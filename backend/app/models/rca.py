"""
RCA (Root Cause Analysis) — SQLAlchemy table + Pydantic schemas.
An incident cannot be CLOSED without a valid RCA.
"""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from . import Base


# ── SQLAlchemy ORM table ────────────────────────────────────────────────────

class RCATable(Base):
    __tablename__ = "rca_reports"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    work_item_id = Column(UUID(as_uuid=False), ForeignKey("work_items.id"), nullable=False)
    root_cause = Column(Text, nullable=False)
    impact = Column(Text, nullable=False)
    resolution = Column(Text, nullable=False)
    prevention = Column(Text, nullable=False)
    incident_start = Column(DateTime(timezone=True), nullable=False)
    incident_end = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(String(100), default="system")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ── Pydantic schemas (API layer) ────────────────────────────────────────────

class RCACreate(BaseModel):
    root_cause: str
    impact: str
    resolution: str
    prevention: str
    incident_start: datetime
    incident_end: datetime
    created_by: str = "system"


class RCAResponse(BaseModel):
    id: str
    work_item_id: str
    root_cause: str
    impact: str
    resolution: str
    prevention: str
    incident_start: datetime
    incident_end: datetime
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}
