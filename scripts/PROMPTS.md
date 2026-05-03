# PROMPTS.md — AI Prompts, Specifications & Planning Notes

> A transparent record of every AI prompt, specification, and architectural decision used to build the Incident Management System. Each section contains the exact prompt text followed by context on what it aimed to achieve.

---

## 1. Project Planning Prompt

```
Design a 4-day development plan for a mission-critical Incident Management System (IMS).

Requirements:
- High-volume signal ingestion from monitoring tools (Prometheus, Datadog, CloudWatch)
  handling 10,000+ signals/sec bursts
- Intelligent debouncing: 100 identical signals should produce 1 Work Item, not 100
- Three-database architecture:
    PostgreSQL — ACID-compliant source of truth for Work Items and RCA reports
    MongoDB    — schema-flexible audit log for every raw signal
    Redis      — Sorted Set dashboard cache + Streams message broker
- State machine workflow: OPEN → INVESTIGATING → RESOLVED → CLOSED
- Severity-based alerting: P0 = PAGE, P1 = NOTIFY, P2 = BATCH
- Mandatory Root Cause Analysis before an incident can be closed
- MTTR (Mean Time to Resolution) auto-calculated on closure
- React frontend with real-time WebSocket updates
- JWT authentication with role-based access control (Admin / Operator / Viewer)
- Full Docker Compose deployment — one command to start everything
- Comprehensive test suite (60+ tests) with mocked databases

Break the plan into:
  Day 1 — Environment setup, project structure, Docker Compose for databases
  Day 2 — Backend: ingestion pipeline, persistence layer, workflow engine, tests
  Day 3 — Frontend: React dashboard, WebSocket integration, RCA form
  Day 4 — Auth, RBAC, dark mode, integration testing, documentation

For each day, list specific deliverables and acceptance criteria.
```

This prompt established the full project scope before any code was written. The 4-day structure forced prioritisation — backend reliability (Day 2) was placed before frontend polish (Day 3) because a beautiful dashboard is worthless if the ingestion pipeline drops signals. The three-database decision was made upfront to avoid a mid-project migration.

---

## 2. Backend Architecture Prompt

```
Build the FastAPI backend for the Incident Management System with these components:

1. Ingestion Endpoint (POST /ingest):
   - Accept single signals or batch arrays (SignalCreate | list[SignalCreate])
   - Rate-limit at 10,000 requests/min using a token-bucket algorithm
   - Return 202 Accepted immediately — decouple HTTP latency from DB writes
   - Queue signals into an asyncio.Queue with maxsize=50,000

2. Signal Processor (background task):
   - Consume from the asyncio.Queue in a continuous loop
   - For each signal: store in MongoDB (audit), publish to Redis Stream (fan-out),
     run through the debouncer
   - Log throughput metrics every 5 seconds (signals/sec, processed count, failures)

3. Debouncer:
   - Generate a debounce key: SHA256(f"{source}|{severity}|{title}")[:16]
   - Check PostgreSQL for an existing OPEN/INVESTIGATING work item with the same key
   - If found → increment signal_count; if not → create new work item
   - 60-second configurable debounce window

4. Retry Decorator (@with_retry):
   - Wrap all database operations (PostgreSQL, MongoDB, Redis)
   - Exponential backoff: base_delay=0.5s, max_retries=3, delays 0.5s → 1s → 2s
   - Retryable: ConnectionError, TimeoutError, OSError + DB-specific exceptions
   - Non-retryable (immediate failure): ValueError, IntegrityError, DuplicateKeyError

5. Rate Limiter:
   - Token bucket algorithm — pure Python, no Redis dependency
   - Must function even if Redis is down (avoids circular failure)
   - Burst-tolerant: allows short spikes as long as average stays within limits

Signal payload schema (Pydantic):
  source: str       — "prometheus", "datadog", "cloudwatch"
  severity: str     — "P0", "P1", "P2"
  title: str        — short alert description
  description: str  — optional, defaults to ""
  metadata: dict    — optional free-form key-value pairs, defaults to {}

Use asyncio throughout — no blocking I/O anywhere in the request path.
```

The core architectural bet was the Producer-Consumer pattern with `asyncio.Queue`. The alternative (Celery + RabbitMQ) was rejected because it adds an entire service to the Docker Compose stack and requires a separate worker process — overkill for a system that can handle its throughput requirements in a single async event loop. The pure-Python rate limiter was a deliberate choice to avoid a circular dependency: if Redis goes down, a Redis-backed rate limiter would also fail, leaving the API completely unprotected during the exact moment it needs protection most.

---

## 3. Database Schema & Persistence Prompt

```
Design the three-database persistence layer for the IMS:

PostgreSQL (Source of Truth — ACID):
  Table: work_items
    id            UUID PRIMARY KEY
    title         VARCHAR NOT NULL
    severity      VARCHAR NOT NULL (P0/P1/P2)
    status        VARCHAR DEFAULT 'OPEN' (OPEN/INVESTIGATING/RESOLVED/CLOSED)
    source        VARCHAR NOT NULL
    debounce_key  VARCHAR NOT NULL (indexed for O(1) lookups)
    signal_count  INTEGER DEFAULT 1
    created_at    TIMESTAMPTZ DEFAULT NOW()
    updated_at    TIMESTAMPTZ DEFAULT NOW()
    closed_at     TIMESTAMPTZ NULL
    mttr_seconds  FLOAT NULL

  Table: rca_reports
    id            UUID PRIMARY KEY
    work_item_id  UUID REFERENCES work_items(id)
    root_cause    TEXT NOT NULL
    impact        TEXT NOT NULL
    resolution    TEXT NOT NULL
    prevention    TEXT NOT NULL
    incident_start TIMESTAMPTZ NOT NULL
    incident_end   TIMESTAMPTZ NOT NULL
    created_by    VARCHAR(100) DEFAULT 'system'
    created_at    TIMESTAMPTZ DEFAULT NOW()

  Table: users
    id            UUID PRIMARY KEY
    full_name     VARCHAR NOT NULL
    email         VARCHAR UNIQUE NOT NULL
    password_hash VARCHAR NOT NULL
    role          VARCHAR DEFAULT 'VIEWER' (ADMIN/OPERATOR/VIEWER)
    designation   VARCHAR DEFAULT 'Engineer'
    is_active     BOOLEAN DEFAULT TRUE
    created_at    TIMESTAMPTZ DEFAULT NOW()

MongoDB (Audit Log — append-only):
  Collection: signals
    signal_id     string (UUID, unique index)
    source        string
    severity      string
    title         string
    description   string
    metadata      object (free-form)
    timestamp     datetime
    processed     boolean
  Indexes: unique on signal_id, compound on (source, severity)

Redis:
  Stream: signal_stream (MAXLEN 10000)
    Fields: signal_id, source, severity, title, payload (JSON)
  Sorted Set: active_incidents
    Score: P0=300, P1=200, P2=100 (severity-based ranking)
    Member: JSON-serialised work item data

Use async drivers throughout: asyncpg (via SQLAlchemy async), Motor, redis.asyncio.
Wrap every operation with @with_retry using database-specific retryable exceptions.
```

The three-database split was the most consequential architectural decision. A single PostgreSQL instance could technically handle everything, but it would force a choice between schema rigidity (bad for raw signals with varying metadata) and schema flexibility (bad for transactional work items). MongoDB's schemaless design handles the variable `metadata` field without ALTER TABLE migrations, while PostgreSQL's ACID guarantees protect the critical state transitions. Redis eliminates SQL queries from the dashboard hot path entirely.

---

## 4. Workflow Engine Prompt

```
Implement the incident lifecycle workflow engine with two design patterns:

1. State Machine (State Pattern):
   States: OPEN, INVESTIGATING, RESOLVED, CLOSED
   Transitions:
     OPEN → INVESTIGATING (only valid forward transition)
     INVESTIGATING → RESOLVED
     RESOLVED → CLOSED (requires RCA to exist — validation guard)
   Rules:
     - CLOSED is a terminal state — no further transitions allowed
     - Invalid transitions raise a clear error with allowed transitions listed
     - Each state is a class that owns its own transition rules (Open-Closed Principle)

2. Alerting (Strategy Pattern):
   Strategies:
     P0 (Critical) → PAGE: "🚨 PAGING ON-CALL: {title}"
     P1 (Warning)  → NOTIFY: "⚠️ NOTIFICATION: {title}"
     P2 (Info)     → BATCH: "📋 BATCHED: {title}"
   The strategy is selected at work item creation based on severity.
   New alert channels (Slack, PagerDuty) can be added by extending the strategy,
   not modifying the router.

3. RCA Validation Guard:
   - Before allowing RESOLVED → CLOSED, query PostgreSQL for an RCA linked
     to the work item
   - If no RCA exists, reject the transition with: "RCA required before closing"
   - This is a domain-level business rule, not an API middleware check

4. MTTR Calculation:
   - On transition to CLOSED: mttr_seconds = (closed_at - created_at).total_seconds()
   - closed_at is set server-side to prevent clock skew from clients
   - MTTR is stored on the work item for dashboard display and SRE reporting
```

The State pattern was chosen over a simple if/else chain because adding new states (e.g., ESCALATED, ON_HOLD) should require adding a new class — not modifying existing transition logic. The RCA guard was deliberately placed inside the state machine rather than in API middleware to make it impossible to bypass, even if someone calls the database layer directly. MTTR is calculated server-side to avoid timezone and clock-skew issues across distributed clients.

---

## 5. Frontend Dashboard Prompt

```
Build a React + Vite dashboard for the Incident Management System:

Components:
  1. Header — app title, user info, dark/light mode toggle, logout
  2. Sidebar — navigation links, incident count badges, user role display
  3. LiveFeed — real-time signal/incident cards sorted by severity then recency
     - P0 cards have a red glow animation to draw operator attention
     - Cards show: title, severity badge, source, status, signal count, timestamp
  4. IncidentDetail — full incident view with timeline, signal history, transition buttons
     - State transition buttons respect RBAC (hidden for Viewers)
     - Shows MTTR when incident is closed
  5. RCAForm — 7 required fields:
     - Root Cause (textarea, 3 rows)
     - Impact (textarea, 2 rows)
     - Resolution (textarea, 2 rows)
     - Prevention (textarea, 2 rows)
     - Incident Start (datetime-local picker)
     - Incident End (datetime-local picker)
     - Author (text input)
     Validation: all fields required, dates converted to ISO 8601 before submission
  6. ActivityPanel — recent system events and signal activity log
  7. CreateIncidentModal — manual incident creation for Admin/Operator roles

Hooks:
  - useWebSocket.js — auto-reconnecting WebSocket to ws://host/ws
    Falls back to 5-second polling if WebSocket is unavailable
  - useTheme.js — dark/light mode with localStorage persistence
    Detects system preference via prefers-color-scheme media query

Auth:
  - LoginPage and SignupPage with JWT-based authentication
  - AuthContext manages token storage, user state, role-based rendering
  - Protected routes: redirect to /login if no valid token
  - Role-based UI: Viewers see read-only dashboard, Operators can transition
    and submit RCA, Admins can manage users

Styling:
  - Dark mode as default (standard for operations dashboards)
  - CSS custom properties (design tokens) for all colors, radii, shadows
  - No CSS framework — vanilla CSS for full control
  - Responsive layout with sidebar collapse on smaller screens
```

The frontend was designed dashboard-first, not form-first. Operations engineers spend 90% of their time watching the LiveFeed, so it received the most design attention (severity sorting, P0 glow, real-time updates). The WebSocket hook includes auto-reconnect because network blips are common in on-call environments — an engineer shouldn't have to manually refresh during an outage. Dark mode is the default because operations dashboards are typically monitored in low-light NOC environments.

---

## 6. Testing Prompt

```
Generate a comprehensive test suite for the IMS backend (64 tests total).
All tests must use mocked databases — no running infrastructure required.

Test files and coverage:

  test_retry.py (8 tests):
    - Successful call returns without retry
    - Retries on retryable exceptions (ConnectionError, TimeoutError, OSError)
    - Exhausts max retries and raises the last exception
    - Exponential backoff delay verification (0.5s, 1.0s, 2.0s)
    - Non-retryable exceptions propagate immediately (ValueError, KeyError)
    - Works with async functions
    - Custom retryable exception list
    - Zero-retry configuration (fail immediately)

  test_rate_limiter.py (7 tests):
    - Allows requests within the rate limit
    - Rejects requests exceeding the rate limit
    - Token replenishment over time
    - Concurrent access safety (asyncio.gather with 100 requests)
    - Burst tolerance — short spikes within average rate
    - Reset functionality
    - Edge case: exactly at the limit boundary

  test_api.py (12 tests):
    - Health check returns status of all 3 databases
    - POST /ingest accepts single signal (202 Accepted)
    - POST /ingest accepts batch signals
    - POST /ingest rejects when rate limited (429)
    - GET /incidents returns work item list
    - GET /incidents/{id} returns detail
    - PATCH /incidents/{id}/transition with valid transition
    - PATCH /incidents/{id}/transition with invalid transition (400)
    - POST /incidents/{id}/rca creates RCA report
    - GET /incidents/{id}/rca retrieves RCA
    - Auth endpoints: signup, login, /auth/me
    - Admin endpoints: list users, change role, disable user

  test_signal_processor.py (4 tests):
    - Processes signal from queue and stores in MongoDB
    - Publishes signal to Redis Stream
    - Throughput metrics counter increments correctly
    - WebSocket broadcast triggered on new incident

  test_debouncer.py (12 tests):
    - Generates correct SHA256 debounce key from (source, severity, title)
    - Same inputs produce same key (deterministic)
    - Different inputs produce different keys
    - First signal creates new work item
    - Subsequent identical signals increment signal_count
    - Different severity creates separate work item
    - Different source creates separate work item
    - Debounce window expiry creates new work item
    - Signal count is correct after multiple debounces
    - Strategy pattern selects correct alert strategy for P0/P1/P2
    - Alert message format verification
    - Edge case: empty title string

  test_state_machine.py (21 tests):
    - OPEN → INVESTIGATING succeeds
    - OPEN → RESOLVED fails (must go through INVESTIGATING)
    - OPEN → CLOSED fails
    - INVESTIGATING → RESOLVED succeeds
    - INVESTIGATING → OPEN fails (no backward transitions)
    - RESOLVED → CLOSED succeeds (with RCA present)
    - RESOLVED → CLOSED fails (no RCA — validation guard)
    - CLOSED → any state fails (terminal state)
    - Each state returns correct allowed transitions list
    - Invalid transition error message includes allowed transitions
    - MTTR calculated correctly on CLOSED transition
    - MTTR is None for non-closed incidents
    - State registry returns correct state handler
    - Unknown state raises error
    - RCA guard queries database correctly
    - Full lifecycle: OPEN → INVESTIGATING → RESOLVED → CLOSED
    - Concurrent transitions are handled safely
    - Transition timestamps are updated
    - closed_at is set on CLOSED transition
    - created_at is preserved across transitions
    - Signal count is independent of state transitions

Use pytest with pytest-asyncio for async tests.
Mock databases using unittest.mock.AsyncMock and patch decorators.
```

The test suite was designed to catch the bugs that matter most in production: retry exhaustion, race conditions in the rate limiter, invalid state transitions, and the RCA validation guard. All tests use mocked databases so they run in <5 seconds with zero infrastructure — critical for CI/CD pipelines. The 21 state machine tests are intentionally exhaustive because a bug in state transitions could leave incidents stuck in limbo with no way to close them.

---

## 7. Key Architectural Decisions & Iterations

### Why PostgreSQL for debounce lookups (not Redis)?

The debounce check and work item creation must be atomic. If we used Redis SET with TTL for debounce keys, a race condition exists: Redis says "no existing key" → we create a work item in PostgreSQL → Redis SET succeeds. But if PostgreSQL fails between the Redis check and the INSERT, we'd have a debounce key in Redis pointing to a work item that doesn't exist. By keeping both operations in PostgreSQL, we get transactional atomicity. Additionally, Redis data is ephemeral — a restart would lose all debounce state and cause duplicate work items.

### Why token bucket over sliding window for rate limiting?

Sliding window rate limiters are more precise but require maintaining a sorted set of timestamps per client — which means Redis dependency. The token bucket is stateless (single counter + timestamp), works in pure Python, and provides burst tolerance by design. During a cascading failure, the monitoring systems fire thousands of signals simultaneously — the token bucket absorbs this burst as long as the average rate stays within limits, while a strict sliding window would reject the first burst entirely and lose critical P0 signals.

### Why WebSocket over Server-Sent Events (SSE)?

SSE is simpler and sufficient for one-way server-to-client updates. However, WebSocket was chosen because it enables future bidirectional features: client-initiated incident acknowledgement, live typing indicators in RCA forms, and operator presence indicators. The additional complexity of WebSocket is minimal with FastAPI's built-in support, and the `useWebSocket.js` hook abstracts all reconnection logic from the components.

### Why asyncio.Queue over Celery + RabbitMQ?

Celery + RabbitMQ adds two services to the infrastructure (RabbitMQ broker + Celery worker), requires a separate process for task execution, and introduces serialisation overhead for every signal. The `asyncio.Queue` is in-process, zero-serialisation, and handles 50,000 buffered signals with no network round-trips. The tradeoff is durability — if the process crashes, queued signals are lost. For a portfolio project this is acceptable; in production, you'd add a dead-letter queue or use Redis Streams as the primary buffer.

### Why CSS custom properties over Tailwind CSS?

Tailwind would have been faster for prototyping but adds a build tooling dependency and makes the CSS harder to reason about in component files. CSS custom properties (design tokens) provide the same consistency benefits — every color, radius, and shadow is defined once in `index.css` and referenced everywhere. This also made the dark mode implementation trivial: swap the token values on `[data-theme="light"]` and every component updates automatically.

### Why three databases instead of one?

A single PostgreSQL instance could technically handle everything, but it would be a poor fit for at least two access patterns. Raw signals are append-only, high-volume, and schema-flexible — MongoDB handles this without ALTER TABLE migrations. Dashboard reads need sub-millisecond latency for the top-K severity-sorted view — Redis Sorted Sets deliver this without a SQL query. PostgreSQL excels at the transactional middle ground: ACID-compliant state transitions and referential integrity between work items and RCA reports. Each database is used for what it does best.

---

## 8. Outage Simulation Script Prompt

```
Create a Python script (scripts/simulate_outage.py) that simulates a realistic
monitoring burst to demonstrate the IMS's debouncing capability.

Send 300 signals to POST /ingest across 3 failure scenarios (100 signals each):

  Scenario 1: RDBMS Outage
    source: "prometheus"
    severity: "P0"
    title: "PostgreSQL primary unreachable"
    100 signals with varying descriptions and metadata (host, region, etc.)

  Scenario 2: Cache Failure
    source: "datadog"
    severity: "P1"
    title: "Redis cluster OOM kill"
    100 signals with different container IDs and memory stats in metadata

  Scenario 3: MCP (Message Control Plane) Failure
    source: "cloudwatch"
    severity: "P2"
    title: "SQS queue depth exceeded threshold"
    100 signals with different queue names and depth values

Expected outcome:
  - 300 signals ingested (all return 202 Accepted)
  - Only 3 Work Items created (one per debounce key)
  - Each Work Item has signal_count = 100
  - All 300 raw signals preserved in MongoDB audit log

The script should:
  - Use aiohttp or httpx for async HTTP requests
  - Print progress (signals sent, response status)
  - Print final summary with work item count verification
  - Target http://localhost:8000/ingest by default (configurable via env var)
  - Complete in under 10 seconds
```

This script serves as both a demo and a smoke test. It validates the core value proposition of the system: 300 noisy signals → 3 actionable work items. The three scenarios were chosen to represent real-world failure modes that SRE teams encounter — database outages, cache failures, and message queue backpressure. Running this script immediately after `docker compose up` provides a compelling visual demonstration of the debouncing, throughput metrics, and live dashboard updates.

---

*This document was created as part of the IMS engineering assignment submission. All prompts reflect the actual specifications and constraints that guided the system's development.*
