# lix-open-search

Open-source AI search engine with web search, video, images, deep research, and RAG-augmented synthesis. Built for self-hosting on commodity hardware.

**Live demo**: [search.elixpo.com](https://search.elixpo.com)

```bash
pip install lix-open-search
```

## What's in this package

| Module | Purpose | Dependencies |
|--------|---------|-------------|
| `lix_open_search` | Python client SDK — sync + async, streaming, multimodal | `httpx` |
| `lix_open_cache` | Multi-layer Redis caching + Huffman disk archival | `redis`, `numpy`, `loguru` |

The SDK connects to a running lixSearch server (self-hosted or `search.elixpo.com`). The cache library works standalone with just Redis.

---

## Search SDK (`lix_open_search`)

### One-shot search

```python
from lix_open_search import LixSearch

lix = LixSearch("http://localhost:9002")

result = lix.search("quantum computing breakthroughs 2026")
print(result.content)
```

### Streaming

```python
for chunk in lix.search_stream("latest advances in fusion energy"):
    print(chunk.content, end="", flush=True)
```

### Multi-turn conversation

```python
result = lix.chat([
    {"role": "user", "content": "Compare Tesla and BYD sales in 2025"}
], session_id="my-session")
print(result.content)

# Follow-up (session remembers context)
result = lix.chat([
    {"role": "user", "content": "Compare Tesla and BYD sales in 2025"},
    {"role": "assistant", "content": result.content},
    {"role": "user", "content": "What about their market cap?"}
], session_id="my-session")
```

### Image + text (multimodal)

```python
result = lix.search(
    "What building is this and when was it built?",
    images=["https://example.com/photo.jpg"]
)
```

### Surf (raw URLs, no LLM)

```python
result = lix.surf("best Python testing frameworks", limit=10, images=True)
print(result.urls)    # ['https://...', ...]
print(result.images)  # ['https://...', ...]
```

### Async

```python
import asyncio
from lix_open_search import AsyncLixSearch

async def main():
    async with AsyncLixSearch("http://localhost:9002") as lix:
        result = await lix.search("SpaceX Starship updates")
        print(result.content)

        async for chunk in lix.search_stream("latest AI papers"):
            print(chunk.content, end="", flush=True)

asyncio.run(main())
```

### Hosted instance

```python
lix = LixSearch("https://search.elixpo.com", api_key="your-key")
```

### OpenAI compatibility

lixSearch is a drop-in OpenAI-compatible API:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:9002/v1", api_key="unused")

response = client.chat.completions.create(
    model="lixsearch",
    messages=[{"role": "user", "content": "latest news on AI regulation"}],
    stream=True,
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### SDK API Reference

**`LixSearch(base_url, api_key=None, timeout=120)`** / **`AsyncLixSearch(...)`**

| Method | Returns | Description |
|--------|---------|-------------|
| `search(query, session_id=, images=)` | `SearchResult` | Search with full LLM synthesis |
| `search_stream(query, session_id=, images=)` | `Iterator[StreamChunk]` | Streaming search |
| `chat(messages, session_id=, stream=)` | `SearchResult` or `Iterator` | Multi-turn conversation |
| `surf(query, limit=5, images=False)` | `SurfResult` | Raw URL + image search (no LLM) |
| `create_session(query)` | `Session` | Create a persistent session |
| `get_session(session_id)` | `Session` | Get session info |
| `get_history(session_id)` | `list[Message]` | Get conversation history |
| `delete_session(session_id)` | `None` | Delete a session |
| `health()` | `dict` | Health check |

### Response models

- **`SearchResult`** — `.content`, `.model`, `.session_id`, `.usage`, `.raw`
- **`StreamChunk`** — `.content`, `.finish_reason`, `.raw`
- **`SurfResult`** — `.urls`, `.images`, `.query`
- **`Session`** / **`Message`** — session and message objects

---

## Cache Library (`lix_open_cache`)

Standalone multi-layer caching for conversational AI. Works independently — just needs Redis.

```python
from lix_open_cache import CacheConfig, CacheCoordinator

config = CacheConfig(redis_host="localhost", redis_port=6379)
cache = CacheCoordinator(session_id="user-abc", config=config)

# Store & retrieve conversation context
cache.add_message_to_context("user", "What's the weather in Tokyo?")
cache.add_message_to_context("assistant", "22C and sunny.")
history = cache.get_context_messages()

# Semantic cache — skip LLM on similar queries
import numpy as np
embedding = np.random.rand(384).astype(np.float32)
cached = cache.get_semantic_response("https://weather.com", embedding)
```

### Three cache layers

| Layer | Purpose | Backend | TTL |
|-------|---------|---------|-----|
| Session Context Window | Rolling 20-message window + disk overflow | Redis DB 2 + `.huff` files | 24h |
| Semantic Query Cache | Deduplicate similar queries (cosine >= 0.90) | Redis DB 0 | 5 min |
| URL Embedding Cache | Cache embedding vectors per URL | Redis DB 1 | 24h |

### Key features

- **Two-tier hybrid storage** — Redis hot window + Huffman-compressed disk cold archive
- **LRU eviction daemon** — auto-migrates idle sessions to disk, re-hydrates on return
- **smart_context()** — recent messages + semantically relevant history from disk
- **Pure Python Huffman codec** — ~54% compression, zero native dependencies
- **CacheConfig dataclass** — all tunables in one place, 12-factor env var support

### Research paper

> **A Three-Layer Caching Architecture for Low-Latency LLM Web Search on Commodity CPU Hardware**
> Ayushman Bhattacharya, 2026
> [Read the paper](https://github.com/Circuit-Overtime/lixSearch/blob/main/docs/paper/lix_cache_paper.pdf)

---

## Self-Hosting with Docker

Run the full lixSearch engine on your own hardware.

### Quick start

```bash
git clone https://github.com/Circuit-Overtime/lixSearch.git
cd lixSearch
cp .env.example .env   # fill in TOKEN, MODEL, HF_TOKEN

# Build and run
docker compose -f package/docker-compose.yml up -d

# Check health
curl http://localhost:9002/api/health

# Scale workers
docker compose -f package/docker-compose.yml up -d --scale app=3
```

### Docker images

| Registry | Image |
|----------|-------|
| GitHub Container Registry | `ghcr.io/circuit-overtime/lixsearch` |
| Docker Hub | `elixpo/lixsearch` |

```bash
docker pull ghcr.io/circuit-overtime/lixsearch:latest
# or
docker pull elixpo/lixsearch:latest
```

### What's in the image

| Service | Port | Purpose |
|---------|------|---------|
| App (Quart API) | 9002 | Search endpoints, OpenAI-compatible API |
| IPC Service | 9510 | Embedding model + Playwright search agents |
| Redis | 9530 | 3-layer cache (sessions, semantic, URL embeddings) |
| ChromaDB | 9001 | Vector database |

### Environment variables

```bash
# Required
TOKEN=your_llm_api_token
MODEL=openai                  # LLM model name
HF_TOKEN=your_huggingface_token

# Optional
IMAGE_MODEL=zimage
VISION_MODEL=gemini-fast
WORKERS=10                    # Hypercorn workers per container
PUBLISHED_PORT=9002           # Host port
REPLICAS=1                    # Number of app containers
REDIS_PASSWORD=your_password
```

### Architecture

```
User / SDK client
    |
    v
App Workers (:9002, N replicas, 10 Hypercorn workers each)
    |-- Pipeline: query decomposition -> tool routing -> RAG -> LLM synthesis
    |-- IPC client -> IPC Service (:9510, singleton)
    |                   |-- Embedding model (sentence-transformers)
    |                   |-- Playwright search agent pool
    |                   |-- ChromaDB (:9001)
    |-- Redis (:9530)
         |-- DB 0: Semantic query cache (5min TTL)
         |-- DB 1: URL embedding cache (24h TTL)
         |-- DB 2: Session context window (20 msgs hot, overflow to disk)
```

---

## Links

- [Live Demo](https://search.elixpo.com)
- [PyPI](https://pypi.org/project/lix-open-search/)
- [GitHub](https://github.com/Circuit-Overtime/lixSearch)
- [Docker Hub](https://hub.docker.com/r/elixpo/lixsearch)
- [Research Paper](https://github.com/Circuit-Overtime/lixSearch/blob/main/docs/paper/lix_cache_paper.pdf)

## License

MIT
