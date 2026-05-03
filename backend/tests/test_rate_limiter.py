"""
Unit tests for the token-bucket rate limiter.
"""

import asyncio
import pytest
from unittest.mock import patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.ingestion.rate_limiter import RateLimiter


class TestRateLimiter:
    """Tests for the token-bucket rate limiter."""

    @pytest.mark.asyncio
    async def test_allows_requests_within_limit(self):
        """Should allow requests when tokens are available."""
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        assert await limiter.acquire() is True
        assert limiter.remaining >= 8  # At least 8 tokens left

    @pytest.mark.asyncio
    async def test_rejects_when_exhausted(self):
        """Should reject requests when all tokens are consumed."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        # Consume all tokens
        assert await limiter.acquire() is True
        assert await limiter.acquire() is True
        assert await limiter.acquire() is True

        # Next request should be rejected
        assert await limiter.acquire() is False

    @pytest.mark.asyncio
    async def test_refills_over_time(self):
        """Tokens should refill proportionally to elapsed time."""
        limiter = RateLimiter(max_requests=100, window_seconds=1)

        # Consume all tokens
        for _ in range(100):
            await limiter.acquire()

        # Should be exhausted
        assert await limiter.acquire() is False

        # Wait for refill (0.1s = 10% of 1s window = ~10 tokens)
        await asyncio.sleep(0.15)

        # Should have tokens again
        assert await limiter.acquire() is True

    @pytest.mark.asyncio
    async def test_remaining_property(self):
        """Remaining property should reflect available tokens."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        initial = limiter.remaining
        assert initial == 5

        await limiter.acquire()
        assert limiter.remaining == 4

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Rate limiter should be safe under concurrent access."""
        limiter = RateLimiter(max_requests=10, window_seconds=60)

        # Fire 20 concurrent requests — only 10 should succeed
        results = await asyncio.gather(
            *[limiter.acquire() for _ in range(20)]
        )

        allowed = sum(1 for r in results if r is True)
        denied = sum(1 for r in results if r is False)

        assert allowed == 10
        assert denied == 10

    @pytest.mark.asyncio
    async def test_never_exceeds_max(self):
        """Token count should never exceed max_requests after refill."""
        limiter = RateLimiter(max_requests=5, window_seconds=1)

        # Wait longer than window for refill
        await asyncio.sleep(0.2)

        # Tokens should be capped at max
        assert limiter.remaining <= 5

    @pytest.mark.asyncio
    async def test_burst_tolerance(self):
        """Should handle burst of requests up to max_requests."""
        limiter = RateLimiter(max_requests=1000, window_seconds=60)

        # Burst of 500 requests — all should succeed
        results = await asyncio.gather(
            *[limiter.acquire() for _ in range(500)]
        )
        assert all(results)
