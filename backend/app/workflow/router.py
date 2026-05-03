"""
Workflow router — incident lifecycle endpoints.

GET  /incidents              → list all work items
GET  /incidents/{id}         → work item detail
GET  /incidents/{id}/signals → raw signals from MongoDB
PATCH /incidents/{id}/transition → state transition
POST /incidents/{id}/rca     → submit Root Cause Analysis
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from ..models.rca import RCACreate, RCAResponse
from ..models.work_item import TransitionRequest, WorkItemResponse
from ..persistence import mongodb, postgres
from .state_machine import transition_work_item
from .strategy import execute_alert

logger = logging.getLogger("ims.workflow")

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get("", response_model=list[WorkItemResponse], summary="List all incidents")
async def list_incidents():
    items = await postgres.list_work_items()
    return items


@router.get("/{item_id}", response_model=WorkItemResponse, summary="Get incident detail")
async def get_incident(item_id: str):
    item = await postgres.get_work_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    return item


@router.get("/{item_id}/signals", summary="Get raw signals for an incident")
async def get_incident_signals(item_id: str):
    """Fetch raw signals from MongoDB that belong to this incident."""
    item = await postgres.get_work_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")

    signals = await mongodb.get_signals_by_debounce_key(
        source=item.source,
        severity=item.severity,
        title=item.title,
    )
    return {"work_item_id": item_id, "signal_count": len(signals), "signals": signals}


@router.patch(
    "/{item_id}/transition",
    response_model=WorkItemResponse,
    summary="Transition incident state",
)
async def transition_incident(item_id: str, body: TransitionRequest):
    """
    OPEN → INVESTIGATING → RESOLVED → CLOSED
    Cannot close without RCA.
    """
    try:
        updated = await transition_work_item(item_id, body.target_status.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Execute alerting strategy on new incidents
    if body.target_status.value == "INVESTIGATING":
        wi_dict = {
            "id": updated.id,
            "title": updated.title,
            "severity": updated.severity,
        }
        alert_result = await execute_alert(wi_dict)
        logger.info("Alert triggered: %s", alert_result)

    return updated


@router.post(
    "/{item_id}/rca",
    response_model=RCAResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Root Cause Analysis",
)
async def submit_rca(item_id: str, body: RCACreate):
    """Submit RCA for an incident. Required before closing."""
    item = await postgres.get_work_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")

    # Check if RCA already exists
    existing = await postgres.get_rca_by_work_item(item_id)
    if existing:
        raise HTTPException(status_code=409, detail="RCA already submitted for this incident")

    rca = await postgres.create_rca(
        work_item_id=item_id,
        root_cause=body.root_cause,
        impact=body.impact,
        resolution=body.resolution,
        prevention=body.prevention,
        incident_start=body.incident_start,
        incident_end=body.incident_end,
        created_by=body.created_by,
    )
    return rca


@router.get("/{item_id}/rca", response_model=RCAResponse, summary="Get RCA for an incident")
async def get_rca(item_id: str):
    rca = await postgres.get_rca_by_work_item(item_id)
    if not rca:
        raise HTTPException(status_code=404, detail="No RCA found for this incident")
    return rca
