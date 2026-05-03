"""
Unit tests for the state machine — validates transition rules and RCA guard.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.workflow.state_machine import (
    OpenState, InvestigatingState, ResolvedState, ClosedState,
    get_state, transition_work_item,
)
from app.models.work_item import WorkItemStatus


# ── State transition rule tests ──────────────────────────────────────────

class TestOpenState:
    def test_name(self):
        assert OpenState().name() == "OPEN"

    def test_allowed_transitions(self):
        assert OpenState().allowed_transitions() == ["INVESTIGATING"]

    def test_rejects_direct_resolve(self):
        state = OpenState()
        assert "RESOLVED" not in state.allowed_transitions()

    def test_rejects_direct_close(self):
        state = OpenState()
        assert "CLOSED" not in state.allowed_transitions()


class TestInvestigatingState:
    def test_name(self):
        assert InvestigatingState().name() == "INVESTIGATING"

    def test_allowed_transitions(self):
        assert InvestigatingState().allowed_transitions() == ["RESOLVED"]

    def test_rejects_direct_close(self):
        state = InvestigatingState()
        assert "CLOSED" not in state.allowed_transitions()


class TestResolvedState:
    def test_name(self):
        assert ResolvedState().name() == "RESOLVED"

    def test_allowed_transitions(self):
        assert ResolvedState().allowed_transitions() == ["CLOSED"]


class TestClosedState:
    def test_name(self):
        assert ClosedState().name() == "CLOSED"

    def test_is_terminal(self):
        assert ClosedState().allowed_transitions() == []


class TestGetState:
    def test_valid_states(self):
        for status in ["OPEN", "INVESTIGATING", "RESOLVED", "CLOSED"]:
            state = get_state(status)
            assert state.name() == status

    def test_invalid_state_raises(self):
        with pytest.raises(ValueError, match="Unknown status"):
            get_state("INVALID")


# ── Transition validation tests ──────────────────────────────────────────

class TestTransitionValidation:
    @pytest.mark.asyncio
    async def test_open_to_investigating_allowed(self):
        state = OpenState()
        with patch('app.workflow.state_machine.postgres') as mock_pg:
            mock_pg.update_work_item_status = AsyncMock(return_value=MagicMock(
                status="INVESTIGATING", created_at=None, closed_at=None
            ))
            result = await state.transition("test-id", "INVESTIGATING")
            assert result is not None

    @pytest.mark.asyncio
    async def test_open_to_resolved_rejected(self):
        state = OpenState()
        with pytest.raises(ValueError, match="Cannot transition"):
            await state.transition("test-id", "RESOLVED")

    @pytest.mark.asyncio
    async def test_open_to_closed_rejected(self):
        state = OpenState()
        with pytest.raises(ValueError, match="Cannot transition"):
            await state.transition("test-id", "CLOSED")

    @pytest.mark.asyncio
    async def test_investigating_to_resolved_allowed(self):
        state = InvestigatingState()
        with patch('app.workflow.state_machine.postgres') as mock_pg:
            mock_pg.update_work_item_status = AsyncMock(return_value=MagicMock(
                status="RESOLVED", created_at=None, closed_at=None
            ))
            result = await state.transition("test-id", "RESOLVED")
            assert result is not None

    @pytest.mark.asyncio
    async def test_investigating_to_closed_rejected(self):
        state = InvestigatingState()
        with pytest.raises(ValueError, match="Cannot transition"):
            await state.transition("test-id", "CLOSED")


# ── RCA validation tests ────────────────────────────────────────────────

class TestRCAValidation:
    @pytest.mark.asyncio
    async def test_close_without_rca_rejected(self):
        """Cannot close an incident without an RCA."""
        with patch('app.workflow.state_machine.postgres') as mock_pg:
            mock_pg.get_work_item = AsyncMock(return_value=MagicMock(
                id="test-id", status="RESOLVED"
            ))
            mock_pg.get_rca_by_work_item = AsyncMock(return_value=None)

            with pytest.raises(ValueError, match="Root Cause Analysis"):
                await transition_work_item("test-id", "CLOSED")

    @pytest.mark.asyncio
    async def test_close_with_rca_allowed(self):
        """Can close an incident when RCA exists."""
        from datetime import datetime, timezone

        mock_item = MagicMock(
            id="test-id", status="RESOLVED",
            created_at=datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc),
            closed_at=datetime(2026, 4, 30, 11, 30, 0, tzinfo=timezone.utc),
            mttr_seconds=None,
        )

        with patch('app.workflow.state_machine.postgres') as mock_pg:
            mock_pg.get_work_item = AsyncMock(return_value=mock_item)
            mock_pg.get_rca_by_work_item = AsyncMock(return_value=MagicMock(id="rca-1"))
            mock_pg.update_work_item_status = AsyncMock(return_value=mock_item)

            result = await transition_work_item("test-id", "CLOSED")
            assert result is not None

    @pytest.mark.asyncio
    async def test_nonexistent_work_item_raises(self):
        """Transitioning a non-existent work item raises ValueError."""
        with patch('app.workflow.state_machine.postgres') as mock_pg:
            mock_pg.get_work_item = AsyncMock(return_value=None)

            with pytest.raises(ValueError, match="not found"):
                await transition_work_item("nonexistent-id", "INVESTIGATING")
