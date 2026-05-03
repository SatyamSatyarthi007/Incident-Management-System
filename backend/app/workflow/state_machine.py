"""
State Machine — each state owns its own transition rules.

State pattern: OPEN → INVESTIGATING → RESOLVED → CLOSED
RCA validation: cannot transition to CLOSED without a valid RCA.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from ..models.work_item import WorkItemStatus
from ..persistence import postgres

logger = logging.getLogger("ims.workflow")


class IncidentState(ABC):
    """Base class for all incident states."""

    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def allowed_transitions(self) -> list[str]: ...

    async def transition(self, work_item_id: str, target: str):
        """Attempt to transition to the target state."""
        if target not in self.allowed_transitions():
            raise ValueError(
                f"Cannot transition from {self.name()} to {target}. "
                f"Allowed: {self.allowed_transitions()}"
            )
        extra = {}
        if target == WorkItemStatus.INVESTIGATING.value:
            extra["acknowledged_at"] = datetime.now(timezone.utc)
        elif target == WorkItemStatus.RESOLVED.value:
            extra["resolved_at"] = datetime.now(timezone.utc)
        elif target == WorkItemStatus.CLOSED.value:
            extra["closed_at"] = datetime.now(timezone.utc)

        updated = await postgres.update_work_item_status(work_item_id, target, **extra)
        logger.info("Work Item %s: %s → %s", work_item_id, self.name(), target)
        return updated


class OpenState(IncidentState):
    def name(self) -> str:
        return WorkItemStatus.OPEN.value

    def allowed_transitions(self) -> list[str]:
        return [WorkItemStatus.INVESTIGATING.value]


class InvestigatingState(IncidentState):
    def name(self) -> str:
        return WorkItemStatus.INVESTIGATING.value

    def allowed_transitions(self) -> list[str]:
        return [WorkItemStatus.RESOLVED.value]


class ResolvedState(IncidentState):
    def name(self) -> str:
        return WorkItemStatus.RESOLVED.value

    def allowed_transitions(self) -> list[str]:
        return [WorkItemStatus.CLOSED.value]


class ClosedState(IncidentState):
    def name(self) -> str:
        return WorkItemStatus.CLOSED.value

    def allowed_transitions(self) -> list[str]:
        return []  # Terminal state


# ── State registry ───────────────────────────────────────────────────────────

_STATES: dict[str, IncidentState] = {
    WorkItemStatus.OPEN.value: OpenState(),
    WorkItemStatus.INVESTIGATING.value: InvestigatingState(),
    WorkItemStatus.RESOLVED.value: ResolvedState(),
    WorkItemStatus.CLOSED.value: ClosedState(),
}


def get_state(status: str) -> IncidentState:
    """Look up the state handler for a given status string."""
    state = _STATES.get(status)
    if not state:
        raise ValueError(f"Unknown status: {status}")
    return state


async def transition_work_item(work_item_id: str, target_status: str):
    """
    Public API — validate and execute a state transition.
    Raises ValueError if the transition is illegal.
    """
    item = await postgres.get_work_item(work_item_id)
    if not item:
        raise ValueError(f"Work item {work_item_id} not found")

    # RCA validation: cannot close without RCA
    if target_status == WorkItemStatus.CLOSED.value:
        rca = await postgres.get_rca_by_work_item(work_item_id)
        if not rca:
            raise ValueError("Cannot close incident without a Root Cause Analysis (RCA)")

    current_state = get_state(item.status)
    updated = await current_state.transition(work_item_id, target_status)

    # Calculate MTTR on closure
    if target_status == WorkItemStatus.CLOSED.value and updated.created_at and updated.closed_at:
        mttr = (updated.closed_at - updated.created_at).total_seconds()
        await postgres.update_work_item_status(work_item_id, target_status, mttr_seconds=mttr)
        updated.mttr_seconds = mttr

    return updated
