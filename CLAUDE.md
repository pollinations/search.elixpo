# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

lixSearch is a multi-service intelligent search assistant (Python/Quart) that searches the web, fetches videos/images, and synthesizes answers with sources. It uses a pipeline architecture with distributed caching, vector embeddings via IPC, and Playwright-based search agents.

## Build & Run

### Docker (production)
```bash
cp .env.example .env          # then fill in TOKEN, MODEL, HF_TOKEN
./deploy.sh build              # build image
./deploy.sh start 3            # start with 3 app containers
./deploy.sh scale 5            # scale to 5
./deploy.sh health             # check all services
./deploy.sh logs app           # tail app logs
./autoscale.sh                 # CPU-based autoscaler daemon (1-5 replicas)
```

### Local development
```bash
source venv/bin/activate       # Python 3.11 venv at /mnt/volume_sfo2_01/lixSearch/venv/
redis-server --port 9530 &     # Redis on custom port
chroma run --host localhost --port 9001 &
APP_MODE=ipc python lixsearch/ipcService/main.py &      # embedding service (port 9510)
APP_MODE=worker WORKER_PORT=9002 python lixsearch/app/main.py &
```

### Tests (integration, no unit test framework)
```bash
python tester/test_multi_turn_session.py
python tester/test_session_persistence.py
python tester/test_redis_semantic_cache.py
```

### Health check
```bash
curl http://localhost:9002/api/health    # direct worker
curl http://localhost/api/health         # via nginx
```

## Architecture

### Network topology

All internal services communicate over a private Docker network (`elixpo-network`). None of the internal 9xxx ports are published to the host — they are only reachable within the Docker network (via `expose`). The only externally reachable entry point is nginx.

```
Internet → Cloudflare → search.elixpo.com
                              │
                              ▼
                     ┌─── nginx ───────────────────────────────┐
                     │  :80    internal/dev (no API key)       │
                     │  :10001 production  (API key required)  │
                     │  :443   reserved (unused currently)     │
                     └────────────┬────────────────────────────┘
                                  │ proxy_pass (Docker internal)
                                  ▼
               lixsearch-app (:9002, N replicas, 10 Hypercorn workers each)
                 ├── Gateways (app/gateways/*.py)
                 ├── Pipeline (pipeline/lixsearch.py) — main async generator
                 │     ├── Tool execution (pipeline/optimized_tool_execution.py)
                 │     ├── RAG (ragService/)
                 │     └── LLM inference → Pollinations API (external)
                 ├── Session/cache (sessions/, ragService/cacheCoordinator.py)
                 ├── PostgreSQL (:5432) — persistent session/conversation storage
                 └── IPC client → ipc-service (:9510, singleton)
                                    ├── CoreEmbeddingService (sentence-transformers)
                                    ├── SearchAgentPool (Playwright text + image agents)
                                    └── Chroma vector DB (:9001)
Redis (:9530) shared across all containers:
  DB 0 — semantic query cache (5min TTL, per-session)
  DB 1 — URL embedding cache (24h TTL, global)
  DB 2 — session hot window (30min TTL, 20 msgs, LRU evicted to disk)
```

### Ports & exposure

| Service | Internal port | Published to host? | Purpose |
|---------|--------------|-------------------|---------|
| nginx | 80, 443, 10001 | **Yes** — 80:80, 443:443, 10001:10001 | Only external entry point |
| lixsearch-app | 9002 | No (`expose` only) | Quart API workers |
| ipc-service | 9510 | No (`expose` only) | Embedding model + Playwright pool |
| chroma-server | 9001 | No (`expose` only) | Vector DB |
| redis | 9530 | No (`expose` only) | Cache (3 DBs) |
| postgres | 5432 | Yes — 5432:5432 (dev admin access) | Persistent storage |

### Authentication

- **Port 80** (nginx internal server): No API key required. Used for local dev and inter-service health checks.
- **Port 10001** (nginx authenticated server): API key required via `X-API-Key` header or `?key=` query param. This is the production endpoint routed from `search.elixpo.com` through Cloudflare.
- **Auth-exempt paths** (both ports): `/api/health`, `/docs`, `/api/docs`, `/openapi.json`, `/openapi.yaml`
- **App-level auth**: `INTERNAL_API_KEY` env var in `before_request` middleware (`app/main.py`). Separate from the nginx API key — used for internal service-to-service calls.

### Request flow
```
User → Cloudflare → nginx:10001 (API key check) → app:9002 → gateway (search.py / chat.py)
  → run_elixposearch_pipeline() async generator → query decomposition → tool routing
  → web_search/fetch/image_search/youtube → RAG retrieval → semantic cache check
  → LLM synthesis → SSE or JSON response
```

### Conversation storage (two-tier hybrid)
- **Hot**: Redis DB 2 — last 20 messages per session
- **Cold**: Huffman-compressed `.huff` files in `./data/conversations/<session_id>.huff`
- LRU eviction daemon migrates idle sessions (30min) from Redis to disk
- Disk archives have 30-day TTL, cleaned on startup

## Key Files

| File | Role |
|------|------|
| `lixsearch/pipeline/lixsearch.py` | Main pipeline orchestrator (~900 lines, async generator) |
| `lixsearch/pipeline/config.py` | **All** configuration constants — edit here, not in service files |
| `lixsearch/pipeline/optimized_tool_execution.py` | Tool routing engine |
| `lixsearch/pipeline/tools.py` | Tool definitions (web_search, fetch_full_text, etc.) |
| `lixsearch/pipeline/instruction.py` | System/user/synthesis prompts |
| `lixsearch/app/main.py` | Quart app with lifecycle hooks |
| `lixsearch/app/gateways/` | HTTP handlers: search.py, chat.py, session.py, health.py |
| `lixsearch/ragService/cacheCoordinator.py` | Orchestrates all 3 Redis cache layers |
| `lixsearch/ragService/semanticCacheRedis.py` | SessionContextWindow, SemanticCacheRedis, URLEmbeddingCache |
| `lixsearch/sessions/hybrid_conversation_cache.py` | Two-tier Redis hot + disk cold cache |
| `lixsearch/sessions/conversation_archive.py` | Huffman-compressed disk persistence |
| `lixsearch/sessions/huffman_codec.py` | Pure Python canonical Huffman codec |
| `lixsearch/ipcService/searchPortManager.py` | Search agent pool (Playwright browsers) |
| `lixsearch/ipcService/coreEmbeddingService.py` | Embedding inference via sentence-transformers |

## Critical Patterns

- **session_id** is the single identifier for all cross-service communication. It must be passed through `memoized_results["session_id"]` for CacheCoordinator and friends. Always `snake_case`, always `str`.
- **Config is centralized**: all tunables live in `pipeline/config.py` with `os.getenv()` overrides. Don't hardcode values in service files.
- **Logging convention**: `loguru` with `[Section]` prefixes — `[Pipeline]`, `[RAG]`, `[Cache]`, `[IPC]`, `[POOL]`, `[APP]`.
- **Pipeline yields strings**: `run_elixposearch_pipeline()` is an async generator. Tools return strings that are yielded progressively to the client.
- **IPC is a singleton**: The `ipc-service` container runs one instance shared by all app replicas. The `SearchAgentPool` inside it has configurable `SEARCH_AGENT_POOL_SIZE` and `SEARCH_AGENT_MAX_TABS` (in config.py).
- **Shared volumes**: All app containers mount the same `conversations-data`, `embeddings-data`, `cache-data` volumes and connect to the same Redis instance. No per-container state.

## Docker Services

| Service | Replicas | Port | Published? | Stateful? |
|---------|----------|------|-----------|-----------|
| nginx | 1 | 80, 443, 10001 | Yes (host-bound) | no |
| lixsearch-app | 1-5 (autoscale) | 9002 | No (internal) | no (shared volumes) |
| ipc-service | 1 | 9510 | No (internal) | no |
| chroma-server | 1 | 9001 | No (internal) | yes (embeddings-data) |
| redis | 1 | 9530 | No (internal) | yes (redis-data) |
| postgres | 1 | 5432 | Yes (dev access) | yes (postgres-data) |

## Environment Variables (.env)

Required: `TOKEN`, `MODEL`, `IMAGE_MODEL`, `HF_TOKEN`
Optional overrides: `REDIS_HOST`, `REDIS_PORT`, `CHROMA_SERVER_HOST`, `CHROMA_SERVER_PORT`, `IPC_HOST`, `IPC_PORT`, `WORKERS` (Hypercorn workers per container, default 10), `WORKER_PORT` (default 9002), `LOG_LEVEL`
