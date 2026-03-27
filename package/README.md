# lixSearch Packages

| Package | Directory | PyPI | Description |
|---------|-----------|------|-------------|
| **lix-open-cache** | [`lix_open_cache_pkg/`](lix_open_cache_pkg/) | [`pip install lix-open-cache`](https://pypi.org/project/lix-open-cache/) | Standalone Redis caching library |

> **Note:** `lix-open-search` was deprecated and removed from PyPI. The search infrastructure lives in the main `lixsearch/` codebase.

## Build & Publish

```bash
./deploy.sh release build cache       # build lix-open-cache
./deploy.sh release pypi cache        # upload lix-open-cache to PyPI
./deploy.sh release docker            # push Docker image
```
