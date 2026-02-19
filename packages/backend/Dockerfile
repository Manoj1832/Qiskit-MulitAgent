# ═══════════════════════════════════════════════════════════════════════════════
# SWE-Agent Chrome Copilot — Backend Dockerfile
# Multi-stage build: dependencies → production / dev / test targets
# ═══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Base ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

LABEL maintainer="SWE-Agent Team"
LABEL description="SWE-Agent Chrome Copilot FastAPI Backend"
LABEL version="1.0.0"

# System deps: git (for GitHub API), curl (healthchecks), build-essential (numpy/faiss)
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        git curl build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1


# ── Stage 2: Production ──────────────────────────────────────────────────────
FROM base AS production

# Copy application code
COPY main.py .
COPY app/ app/

# Create non-root user for security
RUN groupadd -r sweagent && \
    useradd -r -g sweagent -d /app -s /sbin/nologin sweagent && \
    chown -R sweagent:sweagent /app

USER sweagent

# Expose API port
EXPOSE 8000

# Health check — pings /health every 30s
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production entrypoint: Gunicorn with Uvicorn workers
CMD ["python", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--timeout-keep-alive", "120", \
     "--log-level", "info"]


# ── Stage 3: Development (hot-reload) ────────────────────────────────────────
FROM base AS development

# Copy application code
COPY main.py .
COPY app/ app/

# Install dev extras
RUN pip install --no-cache-dir \
    pytest>=8.0.0 \
    pytest-asyncio>=0.23.0 \
    pytest-cov>=5.0.0 \
    httpx>=0.27.0 \
    ruff>=0.4.0

EXPOSE 8000

# Dev entrypoint: Uvicorn with --reload
CMD ["python", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload", \
     "--reload-dir", "/app", \
     "--log-level", "debug"]


# ── Stage 4: Test Runner ─────────────────────────────────────────────────────
FROM development AS test

COPY tests/ tests/

CMD ["python", "-m", "pytest", "tests/", \
     "-v", "--tb=short", "--cov=app", "--cov-report=term-missing"]
