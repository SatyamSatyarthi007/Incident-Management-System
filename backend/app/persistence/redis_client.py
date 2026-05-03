"""
Redis persistence — Streams (message broker) + Sorted Sets (dashboard cache).

All operations are wrapped with exponential-backoff retry to handle
transient failures common in containerised environments.
"""

import json
from typing import Optional

import redis.asyncio as aioredis
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    TimeoutError as RedisTimeoutError,
    BusyLoadingError,
)

from ..config import settings
from .retry import with_retry

# Redis-specific retryable exceptions
_REDIS_RETRYABLE = (
    RedisConnectionError,
    RedisTimeoutError,
    BusyLoadingError,
    ConnectionError,
    ConnectionRefusedError,
    TimeoutError,
    OSError,
)

# ── Client ───────────────────────────────────────────────────────────────────

pool: Optional[aioredis.Redis] = None

STREAM_KEY = "signal_stream"
DASHBOARD_KEY = "active_incidents"


async def init_redis():
    """Create the Redis connection pool on startup."""
    global pool
    pool = aioredis.from_url(settings.redis_dsn, decode_responses=True)


async def close_redis():
    """Close the Redis connection on shutdown."""
    if pool:
        await pool.close()


async def health_check() -> bool:
    """Return True if Redis responds to PING."""
    try:
        return await pool.ping()
    except Exception:
        return False


# ── Stream operations (message broker) ───────────────────────────────────────

@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_REDIS_RETRYABLE)
async def publish_signal(signal_dict: dict) -> str:
    """Publish a signal to Redis Stream. Returns the stream message ID."""
    # Redis streams accept flat key-value pairs
    flat = {
        "signal_id": signal_dict.get("signal_id", ""),
        "source": signal_dict.get("source", ""),
        "severity": signal_dict.get("severity", ""),
        "title": signal_dict.get("title", ""),
        "payload": json.dumps(signal_dict, default=str),
    }
    msg_id = await pool.xadd(STREAM_KEY, flat, maxlen=10000)
    return msg_id


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_REDIS_RETRYABLE)
async def read_stream(last_id: str = "0-0", count: int = 50) -> list[dict]:
    """Read new messages from the signal stream."""
    messages = await pool.xread({STREAM_KEY: last_id}, count=count, block=0)
    results = []
    for _stream, entries in messages:
        for entry_id, data in entries:
            data["_stream_id"] = entry_id
            results.append(data)
    return results


# ── Sorted Set operations (dashboard hot-path cache) ─────────────────────────

SEVERITY_SCORES = {"P0": 300, "P1": 200, "P2": 100}


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_REDIS_RETRYABLE)
async def cache_incident(work_item_id: str, severity: str, data: dict) -> None:
    """Add/update an incident in the dashboard sorted set.
    Score = severity weight so P0 sorts first (highest score).
    """
    score = SEVERITY_SCORES.get(severity, 0)
    await pool.zadd(DASHBOARD_KEY, {json.dumps(data): score})


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_REDIS_RETRYABLE)
async def remove_incident(work_item_id: str) -> None:
    """Remove a resolved/closed incident from the dashboard cache."""
    # Scan members to find the one with matching id
    cursor = 0
    while True:
        cursor, members = await pool.zscan(DASHBOARD_KEY, cursor, match=f'*{work_item_id}*')
        for member, _score in members:
            await pool.zrem(DASHBOARD_KEY, member)
        if cursor == 0:
            break


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_REDIS_RETRYABLE)
async def get_active_incidents(limit: int = 50) -> list[dict]:
    """Fetch active incidents sorted by severity (P0 first)."""
    raw = await pool.zrevrange(DASHBOARD_KEY, 0, limit - 1)
    results = []
    for item in raw:
        try:
            results.append(json.loads(item))
        except json.JSONDecodeError:
            continue
    return results
