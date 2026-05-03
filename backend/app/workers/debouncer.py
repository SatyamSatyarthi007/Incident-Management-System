"""
Debouncer — groups rapid-fire signals into a single Work Item.
100 identical signals within the window → only 1 Work Item created.
"""

import hashlib
import logging
import time
from typing import Optional

from ..config import settings
from ..models.signal import Signal
from ..models.work_item import WorkItemResponse
from ..persistence import postgres, redis_client

logger = logging.getLogger("ims.debouncer")


def make_debounce_key(signal: Signal) -> str:
    """
    Generate a deterministic key from (source, severity, title).
    Signals with the same key within the debounce window are grouped.
    """
    raw = f"{signal.source}|{signal.severity}|{signal.title}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# Simple in-memory tracking of recent debounce keys → timestamps
_recent_keys: dict[str, float] = {}


async def debounce(signal: Signal) -> Optional[dict]:
    """
    Decide whether to create a new Work Item or increment an existing one.

    Returns a dict describing the action taken (for WebSocket broadcast),
    or None if the signal was absorbed by an existing Work Item.
    """
    key = make_debounce_key(signal)
    now = time.time()

    # Clean expired keys
    expired = [k for k, t in _recent_keys.items()
               if now - t > settings.DEBOUNCE_WINDOW_SECONDS]
    for k in expired:
        _recent_keys.pop(k, None)

    # Check if there's already an active work item with this key
    existing = await postgres.find_by_debounce_key(key)

    if existing:
        # Absorb signal into existing work item
        await postgres.increment_signal_count(existing.id)
        _recent_keys[key] = now
        logger.info(
            "Signal %s absorbed into Work Item %s (count: %d)",
            signal.signal_id, existing.id, existing.signal_count + 1,
        )
        return {
            "action": "signal_absorbed",
            "work_item_id": existing.id,
            "signal_count": existing.signal_count + 1,
        }

    # No existing → create a new Work Item
    work_item = await postgres.create_work_item(
        title=signal.title,
        severity=signal.severity,
        source=signal.source,
        debounce_key=key,
    )
    _recent_keys[key] = now

    # Cache in Redis sorted set for dashboard hot-path
    wi_data = {
        "id": work_item.id,
        "title": work_item.title,
        "severity": work_item.severity,
        "status": work_item.status,
        "source": work_item.source,
        "signal_count": work_item.signal_count,
        "created_at": work_item.created_at.isoformat(),
    }
    await redis_client.cache_incident(work_item.id, work_item.severity, wi_data)

    logger.info("New Work Item %s created from signal %s", work_item.id, signal.signal_id)
    return {
        "action": "work_item_created",
        "work_item": wi_data,
    }
