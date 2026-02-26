import hashlib
import threading
import time
from typing import Dict, Optional, List, Tuple, Any
from loguru import logger
import numpy as np
import json
import pickle
from pathlib import Path
from datetime import datetime, timedelta
import os

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("[SemanticCacheRedis] Redis not available, will use fallback file-based cache")


class SemanticQueryCache:
    """Thread-safe in-memory query cache for semantic search results."""
    
    def __init__(self, ttl_seconds: int = 3600, max_size: int = 1000, similarity_threshold: float = 0.98):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.similarity_threshold = similarity_threshold
        
        self.query_cache: Dict[str, Tuple[Any, float, int]] = {}
        self.access_order: List[str] = []
        self.lock = threading.RLock()
        
        logger.info(f"[SemanticQueryCache] Initialized: ttl={ttl_seconds}s, max_size={max_size}, threshold={similarity_threshold}")
    
    def _make_key(self, embedding_hash: str, top_k: int) -> str:
        return f"{embedding_hash}:{top_k}"
    
    def _hash_embedding(self, embedding: np.ndarray) -> str:
        if isinstance(embedding, list):
            embedding = np.array(embedding)
        
        rounded = np.round(embedding, decimals=5)
        hash_input = hashlib.sha256(rounded.tobytes()).hexdigest()
        return hash_input[:16]
    
    def get(self, embedding: np.ndarray, top_k: int = 5) -> Optional[List[Dict]]:
        with self.lock:
            embedding_hash = self._hash_embedding(embedding)
            key = self._make_key(embedding_hash, top_k)
            
            if key not in self.query_cache:
                return None
            
            results, timestamp, access_count = self.query_cache[key]
            
            if time.time() - timestamp > self.ttl_seconds:
                del self.query_cache[key]
                if key in self.access_order:
                    self.access_order.remove(key)
                logger.debug(f"[SemanticQueryCache] Expired: {key}")
                return None
            
            self.query_cache[key] = (results, timestamp, access_count + 1)
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            
            logger.debug(f"[SemanticQueryCache] Hit: {key} (access #{access_count + 1})")
            return results
    
    def set(self, embedding: np.ndarray, top_k: int, results: List[Dict]) -> None:
        with self.lock:
            embedding_hash = self._hash_embedding(embedding)
            key = self._make_key(embedding_hash, top_k)
            
            if len(self.query_cache) >= self.max_size and key not in self.query_cache:
                if self.access_order:
                    oldest_key = self.access_order.pop(0)
                    del self.query_cache[oldest_key]
                    logger.debug(f"[SemanticQueryCache] Evicted: {oldest_key}")
            
            self.query_cache[key] = (results, time.time(), 0)
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            
            logger.debug(f"[SemanticQueryCache] Stored: {key}")
    
    def clear(self) -> None:
        with self.lock:
            self.query_cache.clear()
            self.access_order.clear()
            logger.info("[SemanticQueryCache] Cleared all entries")
    
    def cleanup_expired(self) -> None:
        with self.lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, timestamp, _) in self.query_cache.items()
                if current_time - timestamp > self.ttl_seconds
            ]
            
            for key in expired_keys:
                del self.query_cache[key]
                if key in self.access_order:
                    self.access_order.remove(key)
            
            if expired_keys:
                logger.debug(f"[SemanticQueryCache] Cleaned {len(expired_keys)} expired entries")
    
    def stats(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "cached_queries": len(self.query_cache),
                "max_size": self.max_size,
                "utilization": len(self.query_cache) / self.max_size if self.max_size > 0 else 0,
                "ttl_seconds": self.ttl_seconds
            }


class SemanticCacheRedis:
    """Redis-based semantic cache with fallback to file-based storage."""
    
    def __init__(
        self, 
        ttl_seconds: int = 300, 
        similarity_threshold: float = 0.90, 
        cache_dir: str = "./cache",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0
    ):
        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.redis_client = None
        self.use_redis = False
        self.lock = threading.RLock()
        
        # Try to initialize Redis connection
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=False,
                    socket_connect_timeout=5,
                    socket_keepalive=True
                )
                # Test connection
                self.redis_client.ping()
                self.use_redis = True
                logger.info(f"[SemanticCacheRedis] Connected to Redis @ {redis_host}:{redis_port} (db={redis_db})")
            except Exception as e:
                logger.warning(f"[SemanticCacheRedis] Failed to connect to Redis: {e}. Falling back to file-based cache.")
                self.redis_client = None
                self.use_redis = False
        else:
            logger.warning("[SemanticCacheRedis] Redis not installed. Using file-based cache.")
        
        # Fallback in-memory cache
        self.fallback_cache: Dict[str, Dict] = {}
        self._cleanup_expired_on_startup()
        
        logger.info(f"[SemanticCacheRedis] Initialized: TTL={ttl_seconds}s, threshold={similarity_threshold}, mode={'redis' if self.use_redis else 'file'}")
    
    def _get_request_cache_path(self, request_id: str) -> Path:
        return self.cache_dir / f"cache_{request_id}.pkl"
    
    def _get_redis_key(self, request_id: str, url: str) -> str:
        """Generate a Redis key for caching."""
        return f"semantic_cache:{request_id}:{url}"
    
    def _cleanup_expired_on_startup(self):
        """Clean up expired file-based cache entries on startup."""
        if not self.cache_dir.exists():
            return
        current_time = time.time()
        expired_count = 0
        for cache_file in self.cache_dir.glob("cache_*.pkl"):
            try:
                file_age = current_time - os.path.getmtime(cache_file)
                if file_age > self.ttl_seconds:
                    cache_file.unlink()
                    expired_count += 1
                    request_id = cache_file.stem.replace("cache_", "")
                    logger.info(f"[SemanticCacheRedis] Removed expired cache: {request_id}")
            except Exception as e:
                logger.warning(f"[SemanticCacheRedis] Failed to cleanup {cache_file}: {e}")
        if expired_count > 0:
            logger.info(f"[SemanticCacheRedis] Cleaned up {expired_count} expired cache file(s) on startup")
    
    def _cleanup_runtime(self):
        """Clean up expired in-memory fallback cache entries."""
        with self.lock:
            current_time = time.time()
            expired_urls = []
            for url, url_cache in self.fallback_cache.items():
                expired_keys = [
                    key for key, entry in url_cache.items()
                    if current_time - entry["created_at"] > self.ttl_seconds
                ]
                for key in expired_keys:
                    del url_cache[key]
                if not url_cache:
                    expired_urls.append(url)
            for url in expired_urls:
                del self.fallback_cache[url]
            if expired_urls:
                logger.debug(f"[SemanticCacheRedis] Cleaned up {len(expired_urls)} expired URL entries")
    
    def load_for_request(self, request_id: str) -> bool:
        """Load request-specific cache from storage."""
        if self.use_redis:
            try:
                # Redis doesn't need explicit loading; data is persisted
                logger.info(f"[SemanticCacheRedis] Redis cache ready for request {request_id}")
                return True
            except Exception as e:
                logger.error(f"[SemanticCacheRedis] Failed to prepare Redis cache for {request_id}: {e}")
                return False
        else:
            # File-based fallback
            cache_path = self._get_request_cache_path(request_id)
            if not cache_path.exists():
                logger.debug(f"[SemanticCacheRedis] No cache found for request {request_id}")
                return False
            try:
                with open(cache_path, 'rb') as f:
                    self.fallback_cache = pickle.load(f)
                self._cleanup_runtime()
                logger.info(f"[SemanticCacheRedis] Loaded cache for request {request_id}")
                return True
            except Exception as e:
                logger.error(f"[SemanticCacheRedis] Failed to load cache for {request_id}: {e}")
                return False
    
    def save_for_request(self, request_id: str) -> bool:
        """Save request-specific cache to storage."""
        if self.use_redis:
            try:
                # Redis auto-persists with TTL
                logger.info(f"[SemanticCacheRedis] Redis cache auto-persisted for request {request_id}")
                return True
            except Exception as e:
                logger.error(f"[SemanticCacheRedis] Failed to persist Redis cache for {request_id}: {e}")
                return False
        else:
            # File-based fallback
            cache_path = self._get_request_cache_path(request_id)
            try:
                with self.lock:
                    with open(cache_path, 'wb') as f:
                        pickle.dump(self.fallback_cache, f)
                logger.info(f"[SemanticCacheRedis] Saved cache for request {request_id}")
                return True
            except Exception as e:
                logger.error(f"[SemanticCacheRedis] Failed to save cache for {request_id}: {e}")
                return False
    
    def get(self, url: str, query_embedding: np.ndarray, request_id: str = "default") -> Optional[Dict]:
        """Get cached response for URL and query embedding."""
        with self.lock:
            if self.use_redis:
                return self._get_from_redis(url, query_embedding, request_id)
            else:
                return self._get_from_fallback(url, query_embedding)
    
    def _get_from_redis(self, url: str, query_embedding: np.ndarray, request_id: str) -> Optional[Dict]:
        """Retrieve from Redis cache."""
        try:
            redis_key = self._get_redis_key(request_id, url)
            cached_data = self.redis_client.get(redis_key)
            
            if not cached_data:
                return None
            
            # Decompress cached data
            cache_entry = pickle.loads(cached_data)
            
            # Find best matching embedding
            best_match = None
            best_similarity = 0.0
            
            query_emb = np.array(query_embedding, dtype=np.float32)
            query_emb = query_emb / (np.linalg.norm(query_emb) + 1e-8)
            
            for cached_item in cache_entry["items"]:
                cached_emb = np.array(cached_item["embedding"], dtype=np.float32)
                cached_emb = cached_emb / (np.linalg.norm(cached_emb) + 1e-8)
                similarity = float(np.dot(cached_emb, query_emb))
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = cached_item
            
            if best_similarity >= self.similarity_threshold and best_match:
                logger.debug(f"[SemanticCacheRedis] Redis HIT for {url} (similarity: {best_similarity:.3f})")
                return best_match["response"]
            
            return None
        except Exception as e:
            logger.warning(f"[SemanticCacheRedis] Redis get error for {url}: {e}")
            return None
    
    def _get_from_fallback(self, url: str, query_embedding: np.ndarray) -> Optional[Dict]:
        """Retrieve from fallback file-based cache."""
        if url not in self.fallback_cache:
            return None
        
        url_cache = self.fallback_cache[url]
        current_time = time.time()
        best_match = None
        best_similarity = 0.0
        expired_keys = []
        
        for cache_key, cache_entry in url_cache.items():
            age = current_time - cache_entry["created_at"]
            if age > self.ttl_seconds:
                expired_keys.append(cache_key)
                continue
            
            cached_emb = np.array(cache_entry["query_embedding"], dtype=np.float32)
            query_emb = np.array(query_embedding, dtype=np.float32)
            cached_emb = cached_emb / (np.linalg.norm(cached_emb) + 1e-8)
            query_emb = query_emb / (np.linalg.norm(query_emb) + 1e-8)
            similarity = float(np.dot(cached_emb, query_emb))
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = cache_entry
        
        for key in expired_keys:
            del url_cache[key]
        
        if best_similarity >= self.similarity_threshold and best_match:
            logger.debug(f"[SemanticCacheRedis] Fallback HIT for {url} (similarity: {best_similarity:.3f})")
            return best_match["response"]
        return None
    
    def set(self, url: str, query_embedding: np.ndarray, response: Dict, request_id: str = "default") -> None:
        """Cache response for URL and query embedding."""
        with self.lock:
            if self.use_redis:
                self._set_in_redis(url, query_embedding, response, request_id)
            else:
                self._set_in_fallback(url, query_embedding, response)
    
    def _set_in_redis(self, url: str, query_embedding: np.ndarray, response: Dict, request_id: str) -> None:
        """Store in Redis cache."""
        try:
            redis_key = self._get_redis_key(request_id, url)
            
            # Get existing cache or create new
            cached_data = self.redis_client.get(redis_key)
            if cached_data:
                cache_entry = pickle.loads(cached_data)
            else:
                cache_entry = {"items": []}
            
            # Add new item
            cache_entry["items"].append({
                "embedding": query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding,
                "response": response,
                "timestamp": time.time()
            })
            
            # Keep only last 50 items per URL
            if len(cache_entry["items"]) > 50:
                cache_entry["items"] = cache_entry["items"][-50:]
            
            # Store back in Redis with TTL
            self.redis_client.setex(
                redis_key,
                self.ttl_seconds,
                pickle.dumps(cache_entry)
            )
            logger.debug(f"[SemanticCacheRedis] Stored in Redis: {redis_key}")
        except Exception as e:
            logger.warning(f"[SemanticCacheRedis] Redis set error: {e}")
    
    def _set_in_fallback(self, url: str, query_embedding: np.ndarray, response: Dict) -> None:
        """Store in fallback file-based cache."""
        if url not in self.fallback_cache:
            self.fallback_cache[url] = {}
        
        cache_key = hash(query_embedding.tobytes()) % (2**31)
        self.fallback_cache[url][cache_key] = {
            "query_embedding": query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding,
            "response": response,
            "created_at": time.time()
        }
        
        if len(self.fallback_cache[url]) > 100:
            oldest_key = min(self.fallback_cache[url].keys(), key=lambda k: self.fallback_cache[url][k]["created_at"])
            del self.fallback_cache[url][oldest_key]
    
    def clear_request(self, request_id: str) -> bool:
        """Clear cache for a specific request."""
        if self.use_redis:
            try:
                # Clear all Redis keys for this request
                pattern = self._get_redis_key(request_id, "*")
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
                logger.info(f"[SemanticCacheRedis] Cleared Redis cache for request {request_id}")
                return True
            except Exception as e:
                logger.error(f"[SemanticCacheRedis] Failed to clear Redis cache for {request_id}: {e}")
                return False
        else:
            # File-based fallback
            cache_path = self._get_request_cache_path(request_id)
            try:
                if cache_path.exists():
                    cache_path.unlink()
                with self.lock:
                    self.fallback_cache.clear()
                logger.info(f"[SemanticCacheRedis] Cleared cache for request {request_id}")
                return True
            except Exception as e:
                logger.error(f"[SemanticCacheRedis] Failed to clear cache for {request_id}: {e}")
                return False
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        with self.lock:
            if self.use_redis:
                try:
                    info = self.redis_client.info("memory")
                    return {
                        "backend": "redis",
                        "redis_memory_used": info.get("used_memory_human", "unknown"),
                        "ttl_seconds": self.ttl_seconds,
                        "similarity_threshold": self.similarity_threshold
                    }
                except Exception as e:
                    logger.warning(f"[SemanticCacheRedis] Failed to get Redis stats: {e}")
                    return {
                        "backend": "redis",
                        "status": "error",
                        "error": str(e)
                    }
            else:
                total_entries = sum(len(v) for v in self.fallback_cache.values())
                cache_files = len(list(self.cache_dir.glob("cache_*.pkl")))
                return {
                    "backend": "file",
                    "cached_urls": len(self.fallback_cache),
                    "total_entries": total_entries,
                    "cache_files_on_disk": cache_files,
                    "ttl_seconds": self.ttl_seconds,
                    "similarity_threshold": self.similarity_threshold
                }


# Backward compatibility alias
SemanticCache = SemanticCacheRedis
