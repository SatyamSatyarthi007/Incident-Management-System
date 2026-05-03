"""
Retry decorator with exponential backoff — resilient DB writes.

Handles transient failures that are common in containerised environments:
  - Container startup ordering (backend starts before databases are ready)
  - Transient network partitions between containers
  - Connection pool exhaustion under burst load

Usage:
    @with_retry(max_retries=3, base_delay=0.5)
    async def store_signal(signal_dict: dict) -> None:
        await collection.insert_one(signal_dict)
"""

import asyncio
import functools
import logging
from typing import Callable, Sequence, Type

logger = logging.getLogger("ims.retry")

# Default retryable exceptions — covers all 3 databases
_DEFAULT_RETRYABLE: tuple[Type[Exception], ...] = (
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    TimeoutError,
    OSError,        # Covers socket-level errors in containers
)


def with_retry(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    retryable_exceptions: Sequence[Type[Exception]] | None = None,
):
    """
    Async retry decorator with exponential backoff.

    Args:
        max_retries:          Number of retry attempts before giving up.
        base_delay:           Initial delay (seconds) before first retry.
        max_delay:            Cap on the backoff delay (seconds).
        retryable_exceptions: Exception types that trigger a retry.
                              Defaults to common network/connection errors.
    """
    retry_on = tuple(retryable_exceptions) if retryable_exceptions else _DEFAULT_RETRYABLE

    def decorator(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_retries + 2):  # attempt 1 = initial, +retries
                try:
                    return await fn(*args, **kwargs)
                except retry_on as exc:
                    last_exc = exc
                    if attempt > max_retries:
                        logger.error(
                            "RETRY EXHAUSTED: %s failed after %d attempts: %s",
                            fn.__qualname__, attempt, exc,
                        )
                        raise
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.warning(
                        "RETRY %d/%d: %s raised %s — retrying in %.1fs",
                        attempt, max_retries, fn.__qualname__,
                        type(exc).__name__, delay,
                    )
                    await asyncio.sleep(delay)
            # Should not reach here, but safety net
            raise last_exc  # type: ignore
        return wrapper
    return decorator
