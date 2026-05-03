"""
Token-bucket rate limiter — protects the /ingest endpoint from overload.
"""

import asyncio
import time


class RateLimiter:
    """
    Async token-bucket rate limiter.
    Allows up to `max_requests` in a sliding `window_seconds` window.
    """

    def __init__(self, max_requests: int = 10000, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.tokens = max_requests
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Try to consume one token. Returns True if allowed, False if rate-limited."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill

            # Refill tokens proportionally to elapsed time
            if elapsed > 0:
                refill = (elapsed / self.window) * self.max_requests
                self.tokens = min(self.max_requests, self.tokens + refill)
                self.last_refill = now

            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

    @property
    def remaining(self) -> int:
        return int(self.tokens)
