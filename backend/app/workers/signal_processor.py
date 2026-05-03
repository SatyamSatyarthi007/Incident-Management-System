"""
Signal Processor — background consumer that pulls from asyncio.Queue,
stores raw signals in MongoDB, publishes to Redis Stream, and debounces.

Includes a throughput metrics reporter that logs signals/sec to the console
every 5 seconds (required by assignment spec Section 4).
"""

import asyncio
import logging
import time

from ..persistence import mongodb, redis_client
from .debouncer import debounce

logger = logging.getLogger("ims.processor")
metrics_logger = logging.getLogger("ims.metrics")

# Will be set by main.py on startup
_queue: asyncio.Queue = None
_broadcast_fn = None  # WebSocket broadcast callback

# ── Throughput counters (atomic via GIL) ─────────────────────────────────────

_signals_processed: int = 0
_signals_failed: int = 0


def configure(queue: asyncio.Queue, broadcast_fn=None):
    """Wire the processor to the ingestion queue and optional WS broadcast."""
    global _queue, _broadcast_fn
    _queue = queue
    _broadcast_fn = broadcast_fn


async def _throughput_reporter():
    """
    Background task — prints throughput metrics (signals/sec) to stdout
    every 5 seconds. Works in both local dev and Docker containers
    (visible via `docker logs`).
    """
    global _signals_processed, _signals_failed
    last_count = 0
    last_time = time.monotonic()

    while True:
        await asyncio.sleep(5)
        now = time.monotonic()
        elapsed = now - last_time
        current_count = _signals_processed
        delta = current_count - last_count
        rate = delta / elapsed if elapsed > 0 else 0

        metrics_logger.info(
            "📊 Throughput: %.1f signals/sec | Processed: %d | Failed: %d | Queue depth: %d",
            rate, current_count, _signals_failed,
            _queue.qsize() if _queue else 0,
        )

        last_count = current_count
        last_time = now


async def run():
    """
    Infinite consumer loop — runs as a background asyncio task.

    For each signal:
      1. Store raw signal in MongoDB (audit log)
      2. Publish to Redis Stream (durable fan-out)
      3. Run debouncer → create/update Work Item in PostgreSQL
      4. Broadcast result via WebSocket (if connected)
    """
    global _signals_processed, _signals_failed

    logger.info("Signal processor started — waiting for signals…")

    # Start the throughput reporter as a sibling task
    reporter = asyncio.create_task(_throughput_reporter())

    try:
        while True:
            try:
                signal = await _queue.get()

                # 1. MongoDB audit log
                await mongodb.store_signal(signal.to_mongo_dict())

                # 2. Redis Stream
                await redis_client.publish_signal(signal.to_mongo_dict())

                # 3. Debounce → PostgreSQL
                result = await debounce(signal)

                # 4. WebSocket broadcast
                if result and _broadcast_fn:
                    await _broadcast_fn(result)

                _signals_processed += 1
                _queue.task_done()

            except asyncio.CancelledError:
                raise  # Let cancellation propagate
            except Exception:
                _signals_failed += 1
                logger.exception("Error processing signal")
    except asyncio.CancelledError:
        logger.info("Signal processor shutting down…")
        reporter.cancel()
        try:
            await reporter
        except asyncio.CancelledError:
            pass

