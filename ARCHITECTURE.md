# Architecture Decisions — Incident Management System

## Table of Contents
1. [System Overview](#system-overview)
2. [Why Three Databases?](#why-three-databases)
3. [Signal Ingestion Pipeline](#signal-ingestion-pipeline)
4. [Debouncing Strategy](#debouncing-strategy)
5. [Workflow Engine](#workflow-engine)
6. [Frontend Architecture](#frontend-architecture)
7. [Trade-offs and Alternatives](#trade-offs-and-alternatives)

---

## System Overview

The IMS is designed to handle **high-volume signal ingestion** (10,000+ signals/second bursts) from multiple monitoring sources (Prometheus, Datadog, CloudWatch) and intelligently reduce them into actionable work items that engineers can investigate, resolve, and close with a documented root cause analysis.

### Core Principle: Write-Optimised Ingestion, Read-Optimised Dashboard

The system separates the **write path** (signal ingestion) from the **read path** (dashboard queries) using different storage engines optimised for each access pattern.

---

## Why Three Databases?

### PostgreSQL — Source of Truth (ACID)

**Decision:** Use PostgreSQL for Work Items and RCA reports.

**Rationale:**
- Work items represent business-critical state transitions (OPEN → INVESTIGATING → RESOLVED → CLOSED). These transitions must be **atomic and consistent** — a partial state change is unacceptable.
- RCA reports are legal/compliance documents that must not be lost or corrupted.
- PostgreSQL's ACID guarantees ensure that when we update a work item's status, the change is durable and visible to all subsequent readers immediately.
- The `TIMESTAMPTZ` column type handles timezone-aware datetime correctly across all components.

**Schema Design:**
- `work_items` table uses a `debounce_key` column (indexed) for O(1) lookups during signal grouping.
- `rca_reports` has a foreign key to `work_items`, enforcing referential integrity at the database level.

### MongoDB — Data Lake (Audit Log)

**Decision:** Store every raw signal in MongoDB, regardless of whether it creates a new work item.

**Rationale:**
- Raw signals are **append-only, high-volume, schema-flexible** documents — exactly what MongoDB is optimised for.
- Different monitoring sources may send signals with completely different metadata schemas. MongoDB's schemaless design handles this without ALTER TABLE migrations.
- Signals are never updated, only inserted — MongoDB's write-ahead log and WiredTiger engine provide excellent append throughput.
- We maintain an audit trail: even if 100 signals are debounced into 1 work item, all 100 original signals are preserved for forensic analysis.

**Index Strategy:**
- `signal_id` — unique index for deduplication
- `(source, severity)` — compound index for debounce key lookups

### Redis — Message Broker + Cache

**Decision:** Use Redis for both message brokering (Streams) and dashboard caching (Sorted Sets).

**Rationale:**
- **Redis Streams** provide a durable, append-only log with consumer group support. Unlike in-memory queues, stream entries survive Redis restarts. We use streams for fan-out: multiple consumers can process the same signal for different purposes.
- **Redis Sorted Sets** provide O(log N) insertion and O(1) retrieval of the top-K items. We store active incidents scored by severity (P0=300, P1=200, P2=100), so the dashboard can fetch "top incidents by severity" in a single `ZREVRANGE` call — no SQL query needed.
- Using Redis for both roles avoids adding a separate message broker (RabbitMQ/Kafka) to the stack, keeping the infrastructure simple for a Docker Compose setup.

---

## Signal Ingestion Pipeline

### Architecture: Producer-Consumer with Backpressure

```
HTTP Request → Rate Limiter → asyncio.Queue (50K) → Signal Processor → [MongoDB, Redis, PostgreSQL]
```

### Rate Limiter (Token Bucket)

**Decision:** Implement a token-bucket rate limiter at the API level (10,000 requests/minute).

**Rationale:**
- During cascading failures, monitoring systems can generate explosive signal bursts. Without rate limiting, the API server's connection pool and downstream databases would be overwhelmed.
- Token bucket was chosen over fixed window because it handles **burst tolerance** gracefully — a sudden spike of 1,000 signals is allowed as long as the average rate stays within limits.
- The rate limiter is implemented in pure Python (no Redis dependency) to avoid a circular failure: if Redis is down, the rate limiter still functions.

### asyncio.Queue (In-Memory Buffer)

**Decision:** Use an asyncio.Queue with maxsize=50,000 between the HTTP handler and the signal processor.

**Rationale:**
- This decouples **HTTP response latency** from **database write latency**. The API returns `202 Accepted` in < 1ms while the signal is queued for async processing.
- The 50K buffer absorbs burst traffic: if 10,000 signals arrive in 1 second but the processor handles 5,000/sec, the buffer absorbs the 2-second backlog without dropping signals.
- When the queue is full, signals are dropped with a warning log — this is intentional backpressure. In a production system, you'd add a dead-letter queue, but for this project, the log warning suffices.

### Signal Processor (Background Task)

**Decision:** Run the signal processor as an `asyncio.create_task()` inside the FastAPI lifespan.

**Rationale:**
- Single-process, single-thread async processing is sufficient for our throughput requirements.
- The processor does three things per signal: (1) store in MongoDB, (2) publish to Redis Stream, (3) run debouncer. All three use async I/O, so the event loop is never blocked.

---

## Debouncing Strategy

### Problem

During a "Redis OOM Kill" event, Prometheus might fire the same alert 100 times per minute. We need 100 signals → 1 Work Item.

### Solution: Hash-Based Grouping + Database Lookup

```python
debounce_key = SHA256(f"{source}|{severity}|{title}")[:16]
```

**Decision:** Group signals by `(source, severity, title)` hash and merge into existing open work items.

**Rationale:**
- The hash deterministically maps identical signals to the same key, regardless of description or metadata differences.
- Before creating a new work item, we check PostgreSQL for an existing OPEN or INVESTIGATING work item with the same debounce key. If found, we increment `signal_count` instead of creating a duplicate.
- The 60-second debounce window (configurable) prevents stale grouping: if a "CPU High" alert fires, gets resolved, and fires again 2 hours later, it creates a new work item.

### Why Not Use Redis for Debouncing?

We use PostgreSQL for the debounce lookup because:
1. The debounce key is already indexed in PostgreSQL
2. Work item creation must be atomic with the debounce check (same transaction boundary)
3. Redis data is ephemeral — if Redis restarts, we'd lose debounce state and create duplicate work items

---

## Workflow Engine

### State Machine Pattern

**Decision:** Implement the State pattern where each status (OPEN, INVESTIGATING, RESOLVED, CLOSED) is a class that owns its transition rules.

```
OPEN → INVESTIGATING → RESOLVED → CLOSED (terminal)
```

**Rationale:**
- Adding a new state (e.g., ESCALATED) requires only adding a new class and updating the registry — no modification of existing states. This is the **Open-Closed Principle** in action.
- Each state validates its own allowed transitions. An OPEN incident can only move to INVESTIGATING, never directly to CLOSED. This prevents invalid state transitions at the domain level, not just the API level.

### RCA Validation Guard

**Decision:** The CLOSED state requires a Root Cause Analysis to exist before the transition is allowed.

**Rationale:**
- This is a business rule: incidents cannot be closed without documented root cause, impact, resolution, and prevention steps. Encoding this in the state machine (rather than a middleware or API check) ensures it's impossible to bypass.

### MTTR Calculation

**Decision:** MTTR (Mean Time to Resolution) is auto-calculated as `closed_at - created_at` on closure.

**Rationale:**
- MTTR is the industry-standard SRE metric for incident response quality.
- Calculating it server-side ensures consistency — the dashboard displays the same MTTR regardless of client timezone or clock skew.

### Strategy Pattern (Alerting)

**Decision:** Use the Strategy pattern for severity-based alerting (P0 → PAGE, P1 → NOTIFY, P2 → BATCH).

**Rationale:**
- Alert behaviour varies by severity, and new severity levels or alert channels may be added in the future. The Strategy pattern allows swapping alert logic at runtime without if/else chains.
- Each strategy is a single class with one method: `async alert(work_item)`. Adding Slack, PagerDuty, or email integration is a matter of extending the strategy, not modifying the router.

---

## Frontend Architecture

### Design Decisions

1. **React + Vite** — Vite's Hot Module Replacement provides < 100ms reload during development. React's component model maps naturally to the dashboard's card-based UI.

2. **WebSocket + Polling Fallback** — The WebSocket hook (`useWebSocket.js`) auto-reconnects on disconnect and provides real-time updates. A 5-second polling interval acts as a fallback if WebSocket is unavailable.

3. **Vite Proxy** — In development, Vite proxies `/api/*` to `http://localhost:8000` and `/ws` to `ws://localhost:8000`. This avoids CORS issues without any backend configuration.

4. **CSS Custom Properties (Design Tokens)** — All colors, radii, shadows, and transitions are defined as CSS variables in `index.css`. This enables consistent theming and makes dark mode the default (which is standard for operations dashboards).

5. **Severity-Based Sorting** — The LiveFeed sorts by severity weight (P0=0, P1=1, P2=2), then by status, then by recency. Active P0 cards have a glow animation to draw operator attention.

---

## Trade-offs and Alternatives

| Decision | Alternative | Why We Chose This |
|----------|------------|-------------------|
| asyncio.Queue | Celery + RabbitMQ | Simpler deployment; single-process is sufficient for demo throughput |
| Token bucket rate limiter | Redis-based sliding window | No Redis dependency in the rate limiter; works even if Redis is down |
| SHA256 debounce key | Exact string match | Hash is fixed-length and index-friendly; exact match would require compound index |
| PostgreSQL for debounce lookup | Redis SET with TTL | Atomicity with work item creation; survives Redis restarts |
| WebSocket for live updates | Server-Sent Events (SSE) | WebSocket is bidirectional; allows future features like client-initiated actions |
| CSS custom properties | Tailwind CSS | No build tooling dependency; full control over the design system |
| Monorepo (backend + frontend) | Separate repos | Simplifies Docker Compose and deployment for a portfolio project |
