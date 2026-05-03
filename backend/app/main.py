"""
FastAPI application entry point — wires all layers together.
"""

import asyncio
import json
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .ingestion.router import router as ingest_router, signal_queue
from .workflow.router import router as workflow_router
from .auth.router import router as auth_router
from .admin.router import router as admin_router
from .persistence import postgres, mongodb, redis_client
from .workers import signal_processor

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-20s │ %(levelname)-8s │ %(message)s",
)
logger = logging.getLogger("ims")


# ── WebSocket connection manager ─────────────────────────────────────────────

class ConnectionManager:
    """Manages active WebSocket connections for live dashboard updates."""

    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)
        logger.info("WebSocket client connected (%d total)", len(self.connections))

    def disconnect(self, ws: WebSocket):
        self.connections.remove(ws)
        logger.info("WebSocket client disconnected (%d remain)", len(self.connections))

    async def broadcast(self, data: dict):
        """Send JSON data to all connected clients."""
        message = json.dumps(data, default=str)
        dead = []
        for ws in self.connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)


manager = ConnectionManager()


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    logger.info("🚀 Starting Incident Management System…")

    # Connect databases
    await postgres.init_db()
    await mongodb.init_mongo()
    await redis_client.init_redis()
    logger.info("✅ All databases connected")

    # Wire and start background signal processor
    signal_processor.configure(queue=signal_queue, broadcast_fn=manager.broadcast)
    processor_task = asyncio.create_task(signal_processor.run())
    logger.info("✅ Signal processor running")

    yield  # ── Application is running ──

    # ── Shutdown ──
    logger.info("Shutting down…")
    processor_task.cancel()
    try:
        await processor_task
    except asyncio.CancelledError:
        pass
    await postgres.close_db()
    await mongodb.close_mongo()
    await redis_client.close_redis()
    logger.info("👋 Shutdown complete")


# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Incident Management System",
    description="Mission-critical IMS with signal ingestion, debouncing, "
                "state machine workflow, and live dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(ingest_router)
app.include_router(workflow_router)
app.include_router(auth_router)
app.include_router(admin_router)


# ── WebSocket endpoint ───────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Live dashboard feed — pushes new/updated incidents in real-time."""
    await manager.connect(ws)
    try:
        while True:
            # Keep connection alive; client can also send messages
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── Root ─────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "Incident Management System",
        "version": "1.0.0",
        "docs": "/docs",
    }
