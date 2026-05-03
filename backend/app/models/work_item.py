"""
WorkItem — SQLAlchemy table + Pydantic schemas.
Stored in PostgreSQL as the ACID source of truth.
"""

import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from . import Base


# ── Enums ────────────────────────────────────────────────────────────────────

class WorkItemStatus(str, enum.Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Severity(str, enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


# ── SQLAlchemy ORM table ────────────────────────────────────────────────────

class WorkItemTable(Base):
    __tablename__ = "work_items"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    title = Column(String(500), nullable=False)
    severity = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, default=WorkItemStatus.OPEN.value)
    source = Column(String(200), nullable=False)
    debounce_key = Column(String(255), nullable=False, index=True)
    signal_count = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    mttr_seconds = Column(Float, nullable=True)
    created_by_id = Column(UUID(as_uuid=False), nullable=True)
    created_by_name = Column(String(200), nullable=True, default="system")


# ── Pydantic schemas (API layer) ────────────────────────────────────────────

class WorkItemResponse(BaseModel):
    id: str
    title: str
    severity: str
    status: str
    source: str
    signal_count: int
    created_at: datetime
    updated_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    mttr_seconds: Optional[float] = None
    created_by_id: Optional[str] = None
    created_by_name: Optional[str] = None

    model_config = {"from_attributes": True}


class TransitionRequest(BaseModel):
    target_status: WorkItemStatus
