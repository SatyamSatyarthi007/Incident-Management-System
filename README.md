# Incident Management System (IMS)

> Mission-critical incident management platform with real-time signal ingestion, intelligent debouncing, state machine workflow, and a live React dashboard.

![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql)
![MongoDB](https://img.shields.io/badge/MongoDB-7-47A248?logo=mongodb)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)
![Tests](https://img.shields.io/badge/Tests-64%20passed-brightgreen?logo=pytest)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                   React Dashboard (:5173)                    │
│                                                              │
│  ┌──────────┐  ┌────────────┐  ┌─────────┐  ┌───────────┐    │
│  │ LiveFeed │  │IncidentDtl │  │ RCAForm │  │  StatsBar │    │
│  └─────┬────┘  └──────┬─────┘  └────┬────┘  └───────────┘    │
│        │              │             │                        │
│        └──────────────┼─────────────┘                        │
│                       │ WebSocket + REST                     │
└───────────────────────┼──────────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────────┐
│                 FastAPI Backend (:8000)                      │
│                                                              │
│  ┌──────────────┐      ┌──────────────────┐                  │
│  │ POST /ingest │────▶│  asyncio.Queue   │                  │
│  │ (Rate        │      │  (50K buffer)    │                  │
│  │  Limited)    │      └────────┬─────────┘                  │
│  └──────────────┘               │                            │
│                                 ▼                            │
│                     ┌──────────────────┐                     │
│                     │ Signal Processor │                     │
│                     │   (Background)   │                     │
│                     └──┬──────┬─────┬──┘                     │
│                        │      │     │                        │
│              ┌─────────┘      │     └─────────┐              │
│              ▼                ▼                ▼             │
│  │   MongoDB     │  │ Redis Stream │  │  Debouncer │         │
│  ┌───────────────┐  ┌──────────────┐  ┌────────────┐         │
│  │  (Audit Log)  │  │  (Fan-out)   │  │  (Group)   │         │
│  └───────────────┘  └──────────────┘  └──────┬─────┘         │
│                                              │               │
│                     ┌────────────────────────▼─────┐         │
│                     │ PostgreSQL (Source of Truth)  │        │
│                     │ Work Items + RCA Reports      │        │
│                     └──────────────────────────────┘         │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Workflow Engine                                       │  │
│  │  State Machine: OPEN → INVESTIGATING → RESOLVED →      │  │
│  │                 CLOSED                                 │  │
│  │  Strategy:  P0 = PAGE  |  P1 = NOTIFY  |  P2 = BATCH   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Resilience Layer                                      │  │
│  │  Retry:  Exponential backoff on all DB writes (3x)     │  │
│  │  Metrics: Throughput (signals/sec) logged every 5s     │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Option A: Full Docker (One Command)

```bash
git clone <your-repo-url>
cd incident-management-system

# Start everything — databases, backend, and frontend
docker compose up --build -d
```

- **Dashboard:** http://localhost:80
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

### Option B: Local Development

#### Prerequisites

- [Docker Desktop](https://docker.com/products/docker-desktop) (for databases)
- [Python 3.11+](https://python.org/downloads)
- [Node.js 20+](https://nodejs.org)

#### 1. Start databases

```bash
docker compose up -d postgres mongodb redis
```

#### 2. Start the backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

#### 4. Open the dashboard

- **Dashboard:** http://localhost:5173
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

---

## Simulate an Outage

```bash
python scripts/simulate_outage.py
```

This sends **300 signals** across 3 failure scenarios. Thanks to debouncing, only **3 Work Items** are created (not 300).

---

## Run Tests

```bash
cd backend
python -m pytest tests/ -v
```

**64 tests** covering:

| Test File                  | Tests | Coverage Area                                      |
| -------------------------- | ----- | -------------------------------------------------- |
| `test_retry.py`            | 8     | Exponential backoff, max retries, exception filter |
| `test_rate_limiter.py`     | 7     | Token bucket, concurrency, burst tolerance         |
| `test_api.py`              | 12    | Health, ingestion, incidents, transitions, RCA     |
| `test_signal_processor.py` | 4     | Throughput metrics, counters, WebSocket broadcast  |
| `test_debouncer.py`        | 12    | Key generation, debounce logic, strategy pattern   |
| `test_state_machine.py`    | 21    | State transitions, RCA guard, MTTR                 |

All tests use mocked databases — **no running infrastructure required**.

---

## Backpressure Handling

The system handles high-volume signal bursts (10,000+ signals/sec) through a multi-layered backpressure strategy:

1. **Rate Limiter (Token Bucket):** The `/ingest` endpoint enforces 10,000 requests/min. Excess requests receive `429 Too Many Requests`. Implemented in pure Python — works even if Redis is down.

2. **asyncio.Queue (50K Buffer):** Decouples HTTP response latency from DB write speed. The API returns `202 Accepted` in <1ms while signals queue for async processing.

3. **Backpressure Drop:** When the queue is full, signals are dropped with a warning log. In production, a dead-letter queue would capture these.

4. **Retry with Exponential Backoff:** All database writes (PostgreSQL, MongoDB, Redis) retry up to 3 times with exponential backoff (`0.5s → 1s → 2s`). Handles transient container networking issues.

---

## API Endpoints

| Method  | Path                         | Description                              | Auth     |
| ------- | ---------------------------- | ---------------------------------------- | -------- |
| `POST`  | `/auth/signup`               | Register a new user (first = Admin)      | —        |
| `POST`  | `/auth/login`                | Authenticate and get JWT token           | —        |
| `GET`   | `/auth/me`                   | Get current user profile                 | Bearer   |
| `GET`   | `/health`                    | Health check (PG, Mongo, Redis)          | —        |
| `POST`  | `/ingest`                    | Ingest monitoring signals (rate-limited) | —        |
| `GET`   | `/incidents`                 | List all work items                      | —        |
| `GET`   | `/incidents/{id}`            | Get incident detail                      | —        |
| `PATCH` | `/incidents/{id}/transition` | State machine transition                 | —        |
| `POST`  | `/incidents/{id}/rca`        | Submit Root Cause Analysis               | —        |
| `GET`   | `/incidents/{id}/rca`        | Get RCA for incident                     | —        |
| `GET`   | `/incidents/{id}/signals`    | Get raw signals from MongoDB             | —        |
| `GET`   | `/admin/users`               | List all users                           | Admin    |
| `PATCH` | `/admin/users/{id}/role`     | Change user role                         | Admin    |
| `PATCH` | `/admin/users/{id}/status`   | Enable/disable user account              | Admin    |
| `DELETE`| `/admin/users/{id}`          | Delete a user permanently                | Admin    |
| `WS`    | `/ws`                        | WebSocket live feed                      | —        |

---

## Role-Based Access Control (RBAC)

The system implements a three-tier role hierarchy with JWT-based authentication:

| Permission         | Admin | Operator | Viewer |
|--------------------|:-----:|:--------:|:------:|
| View Dashboard     |   ✅  |    ✅    |   ✅   |
| View Incidents     |   ✅  |    ✅    |   ✅   |
| Create Incidents   |   ✅  |    ✅    |   —    |
| Transition States  |   ✅  |    ✅    |   —    |
| Submit RCA         |   ✅  |    ✅    |   —    |
| Manage Users       |   ✅  |    —     |   —    |
| Change Roles       |   ✅  |    —     |   —    |
| Delete Users       |   ✅  |    —     |   —    |

- **First user** to register is auto-promoted to `ADMIN`
- Subsequent users default to `VIEWER` (admin can promote)
- Passwords are hashed with `bcrypt`
- Sessions persist via `localStorage` JWT tokens (24h expiry)

---

## Tech Stack

| Layer            | Technology       | Purpose                           |
| ---------------- | ---------------- | --------------------------------- |
| Ingestion API    | Python + FastAPI | Async HTTP server, WebSockets     |
| In-Memory Buffer | asyncio.Queue    | Absorbs 10K signals/sec bursts    |
| Message Broker   | Redis Streams    | Durable fan-out to workers        |
| Data Lake        | MongoDB          | Raw signals — audit log           |
| Source of Truth  | PostgreSQL       | Work Items + RCA (ACID)           |
| Cache            | Redis Sorted Set | Dashboard hot-path O(1) reads     |
| Frontend         | React + Vite     | Live dashboard + RCA form         |
| Containers       | Docker Compose   | One-command full-stack deployment |

---

## Design Patterns

| Pattern               | Where Used         | Interview Answer                                                          |
| --------------------- | ------------------ | ------------------------------------------------------------------------- |
| **State**             | Incident lifecycle | Each state (OPEN/INVESTIGATING/RESOLVED/CLOSED) owns its transition rules |
| **Strategy**          | Alerting logic     | Swaps P0/P1/P2 alert behaviour at runtime without if/else chains          |
| **Producer-Consumer** | Signal ingestion   | asyncio.Queue decouples HTTP ingest speed from DB write speed             |
| **Repository**        | Persistence layer  | Database access isolated behind clean async functions                     |
| **Decorator**         | Retry logic        | `@with_retry` wraps all DB operations with exponential backoff            |

---

## Project Structure

```
incident-management-system/
├── docker-compose.yml                # Full stack — DBs + Backend + Frontend
├── README.md                         # This file
├── ARCHITECTURE.md                   # Deep technical decisions
├── PROMPTS.md                        # All AI prompts used
│
├── backend/
│   ├── Dockerfile                    # Multi-stage build with tests
│   ├── requirements.txt              # Python dependencies
│   ├── pyproject.toml                # Pytest configuration
│   ├── tests/
│   │   ├── test_retry.py             # Retry decorator tests (8)
│   │   ├── test_rate_limiter.py      # Token bucket tests (7)
│   │   ├── test_api.py              # API integration tests (12)
│   │   ├── test_signal_processor.py  # Processor + metrics tests (4)
│   │   ├── test_debouncer.py         # Debounce + strategy tests (12)
│   │   └── test_state_machine.py     # State machine + RCA tests (21)
│   └── app/
│       ├── main.py                   # FastAPI entry point + WebSocket
│       ├── config.py                 # Centralised settings (env vars)
│       ├── auth/                     # JWT auth, login, signup, RBAC
│       │   ├── router.py             # /auth endpoints
│       │   ├── dependencies.py       # Role-based dependency injection
│       │   └── jwt_utils.py          # Token encode/decode
│       ├── admin/                    # User management (Admin only)
│       │   └── router.py             # /admin endpoints
│       ├── models/                   # User, Signal, WorkItem, RCA schemas
│       ├── ingestion/                # /ingest endpoint + rate limiter
│       ├── workers/                  # Signal processor + debouncer
│       ├── workflow/                 # State machine + strategy pattern
│       └── persistence/             # PostgreSQL, MongoDB, Redis + retry
│
├── frontend/
│   ├── Dockerfile                    # Vite build → nginx serving
│   ├── nginx.conf                    # SPA routing + API/WS proxy
│   └── src/
│       ├── App.jsx                   # Main layout + protected routing
│       ├── api.js                    # API helper with Bearer token
│       ├── context/AuthContext.jsx   # Auth state management
│       ├── hooks/
│       │   ├── useWebSocket.js       # Live updates
│       │   └── useTheme.js           # Dark/light mode toggle
│       ├── pages/
│       │   ├── LoginPage.jsx         # Authentication
│       │   ├── SignupPage.jsx        # Registration
│       │   └── AdminPanel.jsx        # User management (Admin)
│       └── components/              # Header, LiveFeed, IncidentDetail,
│                                     # RCAForm, Sidebar, ActivityPanel
│
└── scripts/
    ├── test_day2.py                  # Backend E2E verification
    └── simulate_outage.py            # Mock RDBMS + MCP failure (300 signals)
```

---

## Observability

The system prints throughput metrics to stdout every 5 seconds:

```
📊 Throughput: 12.4 signals/sec | Processed: 305 | Failed: 0 | Queue depth: 2
📊 Throughput:  0.0 signals/sec | Processed: 305 | Failed: 0 | Queue depth: 0
```

In Docker, view with: `docker logs -f ims-backend`

---

## License

MIT
