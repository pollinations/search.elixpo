# lix-open-search — self-hostable AI search engine
# https://github.com/elixpo/lixSearch
#
# Build:  cd package && docker compose build
# Run:    cd package && docker compose up -d

# ── Stage 1: Builder ──────────────────────────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright + Chromium for web scraping agents
RUN playwright install --with-deps chromium && \
    find /root/.cache -name "*.pyc" -delete

# ── Stage 2: Runtime ──────────────────────────────────────
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates ffmpeg netcat-traditional && \
    rm -rf /var/lib/apt/lists/*

# Copy Python packages + Playwright browser
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /root/.cache /root/.cache

# Playwright system deps
RUN playwright install-deps chromium 2>/dev/null || true

WORKDIR /app

# Copy application code
COPY lixsearch/ ./lixsearch/
COPY openapi.yaml ./
COPY public/ ./public/
COPY entrypoint.sh ./

# Create data directories
RUN mkdir -p /app/logs /app/models /app/data/cache \
    /app/data/conversations /app/data/embeddings /app/tmp/cache && \
    chmod +x /app/entrypoint.sh

EXPOSE 9002 9510

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${WORKER_PORT:-9002}/api/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
