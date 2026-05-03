"""
API integration tests — tests endpoints using FastAPI's TestClient with mocked databases.

These tests verify the API contract WITHOUT requiring running databases,
making them safe to run in CI/CD pipelines and Docker build stages.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ── Mock database connections before importing the app ───────────────────────
# This prevents the app from trying to connect to real databases on import.

@pytest.fixture
def mock_dbs():
    """Patch all database init/close calls so the app never touches real DBs."""
    with patch('app.persistence.postgres.init_db', new_callable=AsyncMock), \
         patch('app.persistence.postgres.close_db', new_callable=AsyncMock), \
         patch('app.persistence.mongodb.init_mongo', new_callable=AsyncMock), \
         patch('app.persistence.mongodb.close_mongo', new_callable=AsyncMock), \
         patch('app.persistence.redis_client.init_redis', new_callable=AsyncMock), \
         patch('app.persistence.redis_client.close_redis', new_callable=AsyncMock):
        yield


@pytest.fixture
def test_client(mock_dbs):
    """Create a FastAPI TestClient with mocked databases."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Health endpoint ──────────────────────────────────────────────────────────

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_healthy_status(self, test_client):
        """Health check should return healthy when all DBs are up."""
        with patch('app.persistence.postgres.health_check', new_callable=AsyncMock, return_value=True), \
             patch('app.persistence.mongodb.health_check', new_callable=AsyncMock, return_value=True), \
             patch('app.persistence.redis_client.health_check', new_callable=AsyncMock, return_value=True):

            async with test_client as client:
                r = await client.get("/health")

            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "healthy"
            assert data["postgres"] == "up"
            assert data["mongodb"] == "up"
            assert data["redis"] == "up"

    @pytest.mark.asyncio
    async def test_degraded_when_db_down(self, test_client):
        """Health check should return degraded when any DB is down."""
        with patch('app.persistence.postgres.health_check', new_callable=AsyncMock, return_value=True), \
             patch('app.persistence.mongodb.health_check', new_callable=AsyncMock, return_value=False), \
             patch('app.persistence.redis_client.health_check', new_callable=AsyncMock, return_value=True):

            async with test_client as client:
                r = await client.get("/health")

            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "degraded"
            assert data["mongodb"] == "down"


# ── Ingestion endpoint ───────────────────────────────────────────────────────

class TestIngestEndpoint:
    @pytest.mark.asyncio
    async def test_ingest_single_signal(self, test_client):
        """POST /ingest should accept a single signal and return 202."""
        async with test_client as client:
            r = await client.post("/ingest", json={
                "source": "prometheus",
                "severity": "P0",
                "title": "Test Alert",
                "description": "Test signal",
            })

        assert r.status_code == 202
        data = r.json()
        assert data["status"] == "accepted"
        assert data["accepted"] == 1
        assert "queue_depth" in data

    @pytest.mark.asyncio
    async def test_ingest_batch_signals(self, test_client):
        """POST /ingest should accept a batch of signals."""
        signals = [
            {"source": "prometheus", "severity": "P0", "title": f"Alert {i}"}
            for i in range(5)
        ]
        async with test_client as client:
            r = await client.post("/ingest", json=signals)

        assert r.status_code == 202
        data = r.json()
        assert data["accepted"] == 5

    @pytest.mark.asyncio
    async def test_ingest_invalid_payload(self, test_client):
        """POST /ingest with invalid payload should return 422."""
        async with test_client as client:
            r = await client.post("/ingest", json={"invalid": "data"})

        assert r.status_code == 422


# ── Incidents endpoints ──────────────────────────────────────────────────────

class TestIncidentEndpoints:
    @pytest.mark.asyncio
    async def test_list_incidents(self, test_client):
        """GET /incidents should return a list of work items."""
        mock_item = MagicMock(
            id="wi-1", title="Test Alert", severity="P0",
            status="OPEN", source="prometheus", signal_count=5,
            created_at=datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc),
            acknowledged_at=None, resolved_at=None, closed_at=None,
            mttr_seconds=None, created_by_id=None, created_by_name="system",
        )

        with patch('app.persistence.postgres.list_work_items',
                    new_callable=AsyncMock, return_value=[mock_item]):
            async with test_client as client:
                r = await client.get("/incidents")

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "wi-1"
        assert data[0]["severity"] == "P0"

    @pytest.mark.asyncio
    async def test_get_incident_not_found(self, test_client):
        """GET /incidents/{id} for non-existent ID should return 404."""
        with patch('app.persistence.postgres.get_work_item',
                    new_callable=AsyncMock, return_value=None):
            async with test_client as client:
                r = await client.get("/incidents/nonexistent-id")

        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_get_incident_detail(self, test_client):
        """GET /incidents/{id} should return work item details."""
        mock_item = MagicMock(
            id="wi-1", title="Test Alert", severity="P0",
            status="INVESTIGATING", source="prometheus", signal_count=10,
            created_at=datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 30, 10, 30, 0, tzinfo=timezone.utc),
            acknowledged_at=datetime(2026, 4, 30, 10, 5, 0, tzinfo=timezone.utc),
            resolved_at=None, closed_at=None, mttr_seconds=None,
            created_by_id=None, created_by_name="system",
        )

        with patch('app.persistence.postgres.get_work_item',
                    new_callable=AsyncMock, return_value=mock_item):
            async with test_client as client:
                r = await client.get("/incidents/wi-1")

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "INVESTIGATING"
        assert data["signal_count"] == 10


# ── Transition endpoint ──────────────────────────────────────────────────────

class TestTransitionEndpoint:
    @pytest.mark.asyncio
    async def test_invalid_transition_returns_400(self, test_client):
        """Attempting an illegal state transition should return 400."""
        with patch('app.workflow.router.transition_work_item',
                    new_callable=AsyncMock,
                    side_effect=ValueError("Cannot transition from OPEN to CLOSED. Allowed: ['INVESTIGATING']")):
            async with test_client as client:
                r = await client.patch("/incidents/wi-1/transition", json={
                    "target_status": "CLOSED"
                })

        assert r.status_code == 400
        assert "Cannot transition" in r.json()["detail"]


# ── RCA endpoint ─────────────────────────────────────────────────────────────

class TestRCAEndpoint:
    @pytest.mark.asyncio
    async def test_submit_rca(self, test_client):
        """POST /incidents/{id}/rca should create an RCA record."""
        mock_item = MagicMock(id="wi-1")
        mock_rca = MagicMock(
            id="rca-1", work_item_id="wi-1",
            root_cause="OOM", impact="Downtime", resolution="Restarted",
            prevention="Added alerts",
            incident_start=datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc),
            incident_end=datetime(2026, 4, 30, 11, 0, 0, tzinfo=timezone.utc),
            created_by="test", created_at=datetime.now(timezone.utc),
        )

        with patch('app.persistence.postgres.get_work_item',
                    new_callable=AsyncMock, return_value=mock_item), \
             patch('app.persistence.postgres.get_rca_by_work_item',
                    new_callable=AsyncMock, return_value=None), \
             patch('app.persistence.postgres.create_rca',
                    new_callable=AsyncMock, return_value=mock_rca):
            async with test_client as client:
                r = await client.post("/incidents/wi-1/rca", json={
                    "root_cause": "OOM",
                    "impact": "Downtime",
                    "resolution": "Restarted",
                    "prevention": "Added alerts",
                    "incident_start": "2026-04-30T10:00:00Z",
                    "incident_end": "2026-04-30T11:00:00Z",
                    "created_by": "test",
                })

        assert r.status_code == 201
        data = r.json()
        assert data["id"] == "rca-1"
        assert data["root_cause"] == "OOM"

    @pytest.mark.asyncio
    async def test_duplicate_rca_rejected(self, test_client):
        """Submitting RCA twice for same incident should return 409."""
        mock_item = MagicMock(id="wi-1")
        existing_rca = MagicMock(id="rca-existing")

        with patch('app.persistence.postgres.get_work_item',
                    new_callable=AsyncMock, return_value=mock_item), \
             patch('app.persistence.postgres.get_rca_by_work_item',
                    new_callable=AsyncMock, return_value=existing_rca):
            async with test_client as client:
                r = await client.post("/incidents/wi-1/rca", json={
                    "root_cause": "OOM",
                    "impact": "Downtime",
                    "resolution": "Restarted",
                    "prevention": "Added alerts",
                    "incident_start": "2026-04-30T10:00:00Z",
                    "incident_end": "2026-04-30T11:00:00Z",
                })

        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_get_rca_not_found(self, test_client):
        """GET /incidents/{id}/rca when no RCA exists should return 404."""
        with patch('app.persistence.postgres.get_rca_by_work_item',
                    new_callable=AsyncMock, return_value=None):
            async with test_client as client:
                r = await client.get("/incidents/wi-1/rca")

        assert r.status_code == 404
