"""
Signal models — Pydantic only (signals are stored in MongoDB, not PostgreSQL).
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class SignalCreate(BaseModel):
    """Payload accepted by POST /ingest."""
    source: str                # e.g. "prometheus", "datadog", "cloudwatch"
    severity: str              # P0, P1, P2
    title: str
    description: str = ""
    metadata: dict = {}


class Signal(BaseModel):
    """Internal representation after enrichment."""
    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    severity: str
    title: str
    description: str = ""
    metadata: dict = {}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed: bool = False

    def to_mongo_dict(self) -> dict:
        """Serialise for MongoDB insertion."""
        return {
            "signal_id": self.signal_id,
            "source": self.source,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "processed": self.processed,
        }
