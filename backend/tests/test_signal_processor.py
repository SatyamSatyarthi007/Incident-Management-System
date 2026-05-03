"""
Unit tests for the signal processor — validates the throughput metrics
reporter and the processing loop.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.signal import Signal


class TestThroughputReporter:
    """Tests for the throughput metrics background task."""

    @pytest.mark.asyncio
    async def test_reporter_logs_metrics(self):
        """Reporter should log throughput metrics periodically."""
        from app.workers import signal_processor

        # Reset state
        signal_processor._signals_processed = 42
        signal_processor._signals_failed = 2
        signal_processor._queue = asyncio.Queue(maxsize=100)

        with patch.object(signal_processor.metrics_logger, 'info') as mock_log:
            # Start reporter
            task = asyncio.create_task(signal_processor._throughput_reporter())

            # Wait slightly longer than the 5s interval
            # (We mock sleep to speed this up)
            with patch('app.workers.signal_processor.asyncio.sleep',
                       new_callable=AsyncMock) as mock_sleep:
                mock_sleep.side_effect = [None, asyncio.CancelledError()]
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Verify metrics were logged
            assert mock_log.called
            log_msg = mock_log.call_args[0][0]
            assert "Throughput" in log_msg
            assert "signals/sec" in log_msg

    @pytest.mark.asyncio
    async def test_processed_counter_increments(self):
        """Signal processor should increment _signals_processed on success."""
        from app.workers import signal_processor

        # Reset state
        signal_processor._signals_processed = 0
        signal_processor._signals_failed = 0

        queue = asyncio.Queue()
        signal_processor.configure(queue=queue, broadcast_fn=None)

        signal = Signal(source="test", severity="P0", title="Test")
        await queue.put(signal)

        with patch('app.workers.signal_processor.mongodb') as mock_mongo, \
             patch('app.workers.signal_processor.redis_client') as mock_redis, \
             patch('app.workers.signal_processor.debounce', new_callable=AsyncMock, return_value=None):
            mock_mongo.store_signal = AsyncMock()
            mock_redis.publish_signal = AsyncMock()

            # Run processor for a brief moment
            task = asyncio.create_task(signal_processor.run())
            await asyncio.sleep(0.1)  # Let it process the signal
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert signal_processor._signals_processed == 1

    @pytest.mark.asyncio
    async def test_failed_counter_increments_on_error(self):
        """Signal processor should increment _signals_failed on exception."""
        from app.workers import signal_processor

        # Reset state
        signal_processor._signals_processed = 0
        signal_processor._signals_failed = 0

        queue = asyncio.Queue()
        signal_processor.configure(queue=queue, broadcast_fn=None)

        signal = Signal(source="test", severity="P0", title="Test")
        await queue.put(signal)

        with patch('app.workers.signal_processor.mongodb') as mock_mongo, \
             patch('app.workers.signal_processor.redis_client') as mock_redis:
            mock_mongo.store_signal = AsyncMock(side_effect=RuntimeError("DB down"))
            mock_redis.publish_signal = AsyncMock()

            task = asyncio.create_task(signal_processor.run())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert signal_processor._signals_failed >= 1

    @pytest.mark.asyncio
    async def test_broadcast_called_on_debounce_result(self):
        """WebSocket broadcast should be called when debounce returns a result."""
        from app.workers import signal_processor

        signal_processor._signals_processed = 0
        signal_processor._signals_failed = 0

        queue = asyncio.Queue()
        mock_broadcast = AsyncMock()
        signal_processor.configure(queue=queue, broadcast_fn=mock_broadcast)

        signal = Signal(source="test", severity="P0", title="Test")
        await queue.put(signal)

        debounce_result = {"action": "work_item_created", "work_item": {"id": "wi-1"}}

        with patch('app.workers.signal_processor.mongodb') as mock_mongo, \
             patch('app.workers.signal_processor.redis_client') as mock_redis, \
             patch('app.workers.signal_processor.debounce',
                   new_callable=AsyncMock, return_value=debounce_result):
            mock_mongo.store_signal = AsyncMock()
            mock_redis.publish_signal = AsyncMock()

            task = asyncio.create_task(signal_processor.run())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        mock_broadcast.assert_called_once_with(debounce_result)
