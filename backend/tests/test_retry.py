"""
Unit tests for the retry decorator — validates exponential backoff,
max retries, and exception filtering.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.persistence.retry import with_retry


class TestRetryDecorator:
    """Tests for the with_retry decorator."""

    @pytest.mark.asyncio
    async def test_success_without_retry(self):
        """Function that succeeds on first call should not retry."""
        call_count = 0

        @with_retry(max_retries=3)
        async def always_succeeds():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await always_succeeds()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self):
        """Function that fails once then succeeds should retry and return."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def fails_then_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "recovered"

        result = await fails_then_succeeds()
        assert result == "recovered"
        assert call_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_exhausts_retries(self):
        """Function that always fails should raise after max retries."""
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("persistent failure")

        with pytest.raises(ConnectionError, match="persistent failure"):
            await always_fails()

        assert call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_non_retryable_exception_not_retried(self):
        """Non-retryable exceptions should propagate immediately."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01, retryable_exceptions=[ConnectionError])
        async def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            await raises_value_error()

        assert call_count == 1  # No retry for ValueError

    @pytest.mark.asyncio
    async def test_custom_retryable_exceptions(self):
        """Should retry on custom exception types."""
        call_count = 0

        class DatabaseBusy(Exception):
            pass

        @with_retry(max_retries=2, base_delay=0.01, retryable_exceptions=[DatabaseBusy])
        async def busy_db():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise DatabaseBusy("too many connections")
            return "connected"

        result = await busy_db()
        assert result == "connected"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Verify that delays increase exponentially."""
        call_count = 0
        call_times = []

        @with_retry(max_retries=3, base_delay=0.05, max_delay=10.0)
        async def timed_failure():
            nonlocal call_count
            call_count += 1
            call_times.append(asyncio.get_event_loop().time())
            if call_count <= 3:
                raise ConnectionError("fail")
            return "ok"

        result = await timed_failure()
        assert result == "ok"
        assert len(call_times) == 4

        # Verify delays are roughly exponential (0.05, 0.1, 0.2)
        delay1 = call_times[1] - call_times[0]  # ~0.05
        delay2 = call_times[2] - call_times[1]  # ~0.10
        delay3 = call_times[3] - call_times[2]  # ~0.20

        assert delay1 < delay2  # Each delay should be longer
        assert delay2 < delay3

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Backoff should not exceed max_delay."""
        call_count = 0
        call_times = []

        @with_retry(max_retries=5, base_delay=1.0, max_delay=0.05)
        async def capped_failure():
            nonlocal call_count
            call_count += 1
            call_times.append(asyncio.get_event_loop().time())
            if call_count <= 2:
                raise ConnectionError("fail")
            return "ok"

        result = await capped_failure()
        assert result == "ok"

        # Delays should be capped at 0.05s
        for i in range(1, len(call_times)):
            delay = call_times[i] - call_times[i - 1]
            assert delay < 0.2  # Should be ~0.05, allow tolerance

    @pytest.mark.asyncio
    async def test_preserves_function_metadata(self):
        """Decorated function should preserve __name__ and __doc__."""

        @with_retry(max_retries=1)
        async def my_function():
            """My docstring."""
            return True

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."
