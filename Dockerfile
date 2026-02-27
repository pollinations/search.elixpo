FROM python:3.11-slim-bullseye AS builder

ARG BUILDKIT_INLINE_CACHE=1
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

RUN pip install playwright && \
    playwright install chromium && \
    playwright install-deps

# Clean up to reduce layer size
RUN find /usr/local/lib/python3.11/site-packages -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

FROM python:3.11-slim-bullseye

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app \
    REDIS_PORT=6380

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    ffmpeg \
    netcat \
    redis-server \
    redis-tools \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY lixsearch /app/lixsearch
COPY tester /app/tester
COPY entrypoint.sh /app/entrypoint.sh
COPY version.cfg requirements.txt /app/

RUN chmod +x /app/entrypoint.sh && \
    mkdir -p /app/logs /app/cache && \
    chown -R nobody:nogroup /app

RUN useradd -m -u 1000 elixpo && \
    chown -R elixpo:elixpo /app

USER elixpo

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
    CMD curl -f http://localhost:${WORKER_PORT:-8001}/api/health || exit 1

EXPOSE 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010

ENTRYPOINT ["/app/entrypoint.sh"]
