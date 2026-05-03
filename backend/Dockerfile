# ── Stage 1: Builder (install deps + run tests) ────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Run unit tests during build — fail the build if tests fail
RUN python -m pytest tests/ -v --tb=short

# ── Stage 2: Production runtime ────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Security: run as non-root user
RUN groupadd -r ims && useradd -r -g ims -s /sbin/nologin ims

WORKDIR /app

# Install only production dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (no test files in production image)
COPY app/ ./app/

# Switch to non-root user
USER ims

# Expose FastAPI port
EXPOSE 8000

# Health check — uses the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Start uvicorn — 0.0.0.0 binds to all interfaces (required in Docker)
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
