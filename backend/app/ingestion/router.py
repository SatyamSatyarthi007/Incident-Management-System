"""
Ingestion router — POST /ingest (high-volume signal intake) + GET /health.
"""

import asyncio
import logging
from typing import Union

from fastapi import APIRouter, HTTPException, status

from ..config import settings
from ..models.signal import Signal, SignalCreate
from ..persistence import mongodb, postgres, redis_client
from .rate_limiter import RateLimiter

logger = logging.getLogger("ims.ingestion")

router = APIRouter(tags=["Ingestion"])

# ── Shared state ─────────────────────────────────────────────────────────────

rate_limiter = RateLimiter(
    max_requests=settings.RATE_LIMIT_MAX,
    window_seconds=settings.RATE_LIMIT_WINDOW,
)

# The asyncio.Queue that decouples HTTP speed from DB write speed
# (Producer-Consumer pattern)
signal_queue: asyncio.Queue = asyncio.Queue(maxsize=50_000)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a monitoring signal",
)
async def ingest_signal(payload: Union[SignalCreate, list[SignalCreate]]):
    """
    Accept one or more signals at high volume.
    Signals are placed onto an in-memory asyncio.Queue for async processing.
    """
    # Rate-limit check
    if not await rate_limiter.acquire():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded ({settings.RATE_LIMIT_MAX}/min). Retry later.",
        )

    # Normalise to list
    signals = payload if isinstance(payload, list) else [payload]
    accepted = 0

    for s in signals:
        enriched = Signal(
            source=s.source,
            severity=s.severity.upper(),
            title=s.title,
            description=s.description,
            metadata=s.metadata,
        )
        try:
            signal_queue.put_nowait(enriched)
            accepted += 1
        except asyncio.QueueFull:
            logger.warning("Signal queue full — dropping signal %s", enriched.signal_id)

    return {
        "status": "accepted",
        "accepted": accepted,
        "queue_depth": signal_queue.qsize(),
    }


@router.get("/health", summary="Health check for all databases")
async def health():
    """Return connectivity status of PostgreSQL, MongoDB, and Redis."""
    pg = await postgres.health_check()
    mongo = await mongodb.health_check()
    redis = await redis_client.health_check()

    all_healthy = pg and mongo and redis
    return {
        "status": "healthy" if all_healthy else "degraded",
        "postgres": "up" if pg else "down",
        "mongodb": "up" if mongo else "down",
        "redis": "up" if redis else "down",
    }
