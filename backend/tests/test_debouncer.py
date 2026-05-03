"""
Unit tests for the debouncer — validates key generation and grouping logic.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.workers.debouncer import make_debounce_key, debounce
from app.models.signal import Signal


# ── Debounce key tests ───────────────────────────────────────────────────

class TestDebounceKey:
    def test_same_signals_same_key(self):
        """Identical (source, severity, title) produce the same key."""
        s1 = Signal(source="prometheus", severity="P0", title="CPU High")
        s2 = Signal(source="prometheus", severity="P0", title="CPU High",
                    description="Different description")
        assert make_debounce_key(s1) == make_debounce_key(s2)

    def test_different_source_different_key(self):
        s1 = Signal(source="prometheus", severity="P0", title="CPU High")
        s2 = Signal(source="datadog", severity="P0", title="CPU High")
        assert make_debounce_key(s1) != make_debounce_key(s2)

    def test_different_severity_different_key(self):
        s1 = Signal(source="prometheus", severity="P0", title="CPU High")
        s2 = Signal(source="prometheus", severity="P1", title="CPU High")
        assert make_debounce_key(s1) != make_debounce_key(s2)

    def test_different_title_different_key(self):
        s1 = Signal(source="prometheus", severity="P0", title="CPU High")
        s2 = Signal(source="prometheus", severity="P0", title="Memory High")
        assert make_debounce_key(s1) != make_debounce_key(s2)

    def test_case_insensitive(self):
        """Keys should be case-insensitive."""
        s1 = Signal(source="Prometheus", severity="P0", title="CPU HIGH")
        s2 = Signal(source="prometheus", severity="p0", title="cpu high")
        assert make_debounce_key(s1) == make_debounce_key(s2)

    def test_key_is_16_chars(self):
        """Key should be truncated to 16 hex characters."""
        s = Signal(source="prometheus", severity="P0", title="Test")
        key = make_debounce_key(s)
        assert len(key) == 16
        assert all(c in '0123456789abcdef' for c in key)


# ── Debounce logic tests ────────────────────────────────────────────────

class TestDebounceLogic:
    @pytest.mark.asyncio
    async def test_new_signal_creates_work_item(self):
        """A signal with no matching work item creates a new one."""
        signal = Signal(source="prometheus", severity="P0", title="Test Alert")

        with patch('app.workers.debouncer.postgres') as mock_pg, \
             patch('app.workers.debouncer.redis_client') as mock_redis:

            mock_pg.find_by_debounce_key = AsyncMock(return_value=None)
            mock_pg.create_work_item = AsyncMock(return_value=MagicMock(
                id="wi-1", title="Test Alert", severity="P0",
                status="OPEN", source="prometheus", signal_count=1,
                created_at=MagicMock(isoformat=lambda: "2026-04-30T10:00:00"),
            ))
            mock_redis.cache_incident = AsyncMock()

            result = await debounce(signal)

            assert result is not None
            assert result["action"] == "work_item_created"
            mock_pg.create_work_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_signal_increments_count(self):
        """A signal matching an existing work item increments signal_count."""
        signal = Signal(source="prometheus", severity="P0", title="Test Alert")

        existing = MagicMock(id="wi-1", signal_count=3)

        with patch('app.workers.debouncer.postgres') as mock_pg:
            mock_pg.find_by_debounce_key = AsyncMock(return_value=existing)
            mock_pg.increment_signal_count = AsyncMock()

            result = await debounce(signal)

            assert result is not None
            assert result["action"] == "signal_absorbed"
            assert result["signal_count"] == 4
            mock_pg.increment_signal_count.assert_called_once_with("wi-1")


# ── Strategy pattern tests ──────────────────────────────────────────────

class TestAlertStrategy:
    @pytest.mark.asyncio
    async def test_p0_pages_oncall(self):
        from app.workflow.strategy import execute_alert
        result = await execute_alert({"severity": "P0", "title": "Test"})
        assert result["action"] == "PAGE_ONCALL"
        assert result["urgency"] == "immediate"

    @pytest.mark.asyncio
    async def test_p1_notifies_team(self):
        from app.workflow.strategy import execute_alert
        result = await execute_alert({"severity": "P1", "title": "Test"})
        assert result["action"] == "NOTIFY_TEAM"
        assert result["urgency"] == "5_minutes"

    @pytest.mark.asyncio
    async def test_p2_batches_digest(self):
        from app.workflow.strategy import execute_alert
        result = await execute_alert({"severity": "P2", "title": "Test"})
        assert result["action"] == "BATCH_DIGEST"
        assert result["urgency"] == "hourly"

    @pytest.mark.asyncio
    async def test_unknown_severity_defaults_to_p2(self):
        from app.workflow.strategy import execute_alert
        result = await execute_alert({"severity": "P9", "title": "Test"})
        assert result["action"] == "BATCH_DIGEST"
