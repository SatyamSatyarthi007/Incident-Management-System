"""
MongoDB persistence — Motor async client for raw signal storage (audit log).

All write operations are wrapped with exponential-backoff retry to handle
transient failures common in containerised environments (e.g. DNS resolution
lag, container startup ordering, network partitions).
"""

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import (
    AutoReconnect,
    ConnectionFailure,
    NetworkTimeout,
    ServerSelectionTimeoutError,
)

from ..config import settings
from .retry import with_retry

# Mongo-specific retryable exceptions
_MONGO_RETRYABLE = (
    AutoReconnect,
    ConnectionFailure,
    NetworkTimeout,
    ServerSelectionTimeoutError,
    ConnectionError,
    TimeoutError,
    OSError,
)

# ── Client & collections ────────────────────────────────────────────────────

client: Optional[AsyncIOMotorClient] = None
db = None
signals_collection = None


async def init_mongo():
    """Connect to MongoDB on startup."""
    global client, db, signals_collection
    client = AsyncIOMotorClient(settings.mongodb_dsn)
    db = client[settings.MONGODB_DB]
    signals_collection = db["signals"]
    # Create index on signal_id for fast lookups
    await signals_collection.create_index("signal_id", unique=True)
    # Index on debounce fields for grouping
    await signals_collection.create_index([("source", 1), ("severity", 1)])


async def close_mongo():
    """Close the MongoDB connection on shutdown."""
    global client
    if client:
        client.close()


async def health_check() -> bool:
    """Return True if MongoDB is reachable."""
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        return False


# ── Signal operations (with retry) ───────────────────────────────────────────

@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_MONGO_RETRYABLE)
async def store_signal(signal_dict: dict) -> None:
    """Insert a raw signal document into the audit log."""
    await signals_collection.insert_one(signal_dict)


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_MONGO_RETRYABLE)
async def get_signals_by_source(source: str, limit: int = 100) -> list[dict]:
    """Retrieve recent signals from a given source."""
    cursor = signals_collection.find(
        {"source": source}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit)
    return await cursor.to_list(length=limit)


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_MONGO_RETRYABLE)
async def get_signals_by_debounce_key(
    source: str, severity: str, title: str, limit: int = 200
) -> list[dict]:
    """Retrieve signals matching a debounce group."""
    cursor = signals_collection.find(
        {"source": source, "severity": severity, "title": title},
        {"_id": 0},
    ).sort("timestamp", -1).limit(limit)
    return await cursor.to_list(length=limit)


@with_retry(max_retries=3, base_delay=0.5, retryable_exceptions=_MONGO_RETRYABLE)
async def get_all_signals(limit: int = 500) -> list[dict]:
    """Retrieve most recent signals across all sources."""
    cursor = signals_collection.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit)
    return await cursor.to_list(length=limit)
