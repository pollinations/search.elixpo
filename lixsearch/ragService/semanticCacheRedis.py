import hashlib
import threading
import time
from typing import Dict, Optional, List, Tuple, Any
from loguru import logger
import numpy as np
import pickle
from datetime import datetime

# Import centralized config
from pipeline.config import (
    SEMANTIC_CACHE_REDIS_HOST,
    SEMANTIC_CACHE_REDIS_PORT,
    SEMANTIC_CACHE_REDIS_DB,
    SEMANTIC_CACHE_REDIS_TTL_SECONDS,
    SEMANTIC_CACHE_REDIS_SIMILARITY_THRESHOLD,
    SEMANTIC_CACHE_REDIS_MAX_ITEMS_PER_URL,
    SEMANTIC_CACHE_REDIS_POOL_SIZE,
    URL_EMBEDDING_CACHE_REDIS_DB,
    URL_EMBEDDING_CACHE_TTL_SECONDS,
    URL_EMBEDDING_CACHE_BATCH_SIZE,
    SESSION_CONTEXT_WINDOW_REDIS_DB,
    SESSION_CONTEXT_WINDOW_TTL_SECONDS,
    SESSION_CONTEXT_WINDOW_SIZE,
    SESSION_CONTEXT_WINDOW_MAX_TOKENS,
    REDIS_SOCKET_CONNECT_TIMEOUT,
    REDIS_SOCKET_KEEPALIVE,
    REDIS_KEY_PREFIX,
)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.error("[semanticCacheRedis] Redis not available - Redis is REQUIRED for optimized caching")


class URLEmbeddingCache:
    """
    Persistent URL embedding cache (24h TTL).
    Stores single embedding per URL, reused across all sessions.
    Default: Redis DB 1
    """
    
    def __init__(
        self,
        session_id: str,
        ttl_seconds: int = URL_EMBEDDING_CACHE_TTL_SECONDS,
        redis_host: str = SEMANTIC_CACHE_REDIS_HOST,
        redis_port: int = SEMANTIC_CACHE_REDIS_PORT,
        redis_db: int = URL_EMBEDDING_CACHE_REDIS_DB,
        batch_size: int = URL_EMBEDDING_CACHE_BATCH_SIZE
    ):
        self.session_id = session_id
        self.ttl_seconds = ttl_seconds
        self.batch_size = batch_size
        self.redis_client = None
        self.lock = threading.RLock()
        
        if not REDIS_AVAILABLE:
            raise RuntimeError("[semanticCacheRedis.URLEmbeddingCache] Redis is required but not installed")
        
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=False,
                socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
                socket_keepalive=REDIS_SOCKET_KEEPALIVE
            )
            self.redis_client.ping()
            logger.info(f"[semanticCacheRedis.URLEmbeddingCache] session={session_id} connected to Redis @ {redis_host}:{redis_port} (db={redis_db})")
        except Exception as e:
            logger.error(f"[semanticCacheRedis.URLEmbeddingCache] session={session_id} Failed to connect: {e}")
            raise
    
    def _get_key(self, url: str) -> str:
        """Generate Redis key: url_embedding:URL_HASH"""
        return f"{REDIS_KEY_PREFIX}:url_embedding:{url}"
    
    def get(self, url: str) -> Optional[np.ndarray]:
        """Retrieve cached URL embedding"""
        with self.lock:
            try:
                key = self._get_key(url)
                cached = self.redis_client.get(key)
                if cached:
                    embedding = np.frombuffer(cached, dtype=np.float32)
                    logger.debug(f"[semanticCacheRedis.URLEmbeddingCache] session={self.session_id} HIT: {url}")
                    return embedding
                return None
            except Exception as e:
                logger.warning(f"[semanticCacheRedis.URLEmbeddingCache] session={self.session_id} Get error for {url}: {e}")
                return None
    
    def set(self, url: str, embedding: np.ndarray) -> bool:
        """Store URL embedding with TTL"""
        with self.lock:
            try:
                key = self._get_key(url)
                if isinstance(embedding, np.ndarray):
                    embedding_bytes = embedding.astype(np.float32).tobytes()
                else:
                    embedding = np.array(embedding, dtype=np.float32)
                    embedding_bytes = embedding.tobytes()
                
                self.redis_client.setex(key, self.ttl_seconds, embedding_bytes)
                logger.debug(f"[semanticCacheRedis.URLEmbeddingCache] session={self.session_id} STORED: {url}")
                return True
            except Exception as e:
                logger.warning(f"[semanticCacheRedis.URLEmbeddingCache] session={self.session_id} Set error for {url}: {e}")
                return False
    
    def batch_set(self, url_embeddings: Dict[str, np.ndarray]) -> Dict[str, bool]:
        """Store multiple embeddings efficiently"""
        results = {}
        with self.lock:
            for url, embedding in url_embeddings.items():
                results[url] = self.set(url, embedding)
        return results
    
    def get_stats(self) -> Dict:
        try:
            info = self.redis_client.info("memory")
            return {
                "backend": "redis",
                "session_id": self.session_id,
                "redis_memory_used": info.get("used_memory_human", "unknown"),
                "ttl_seconds": self.ttl_seconds,
                "batch_size": self.batch_size
            }
        except Exception as e:
            logger.warning(f"[semanticCacheRedis.URLEmbeddingCache] session={self.session_id} Failed to get stats: {e}")
            return {"backend": "redis", "status": "error"}


class SessionContextWindow:
    """
    Per-session conversation context window (LRU, TTL-based).
    Stores recent messages to provide context for LLM inference.
    Default: Redis DB 2, 20 messages/window, TTL 30min
    Scalable to 100+ messages per session for future growth.
    """
    
    def __init__(
        self,
        session_id: str,
        window_size: int = SESSION_CONTEXT_WINDOW_SIZE,
        ttl_seconds: int = SESSION_CONTEXT_WINDOW_TTL_SECONDS,
        max_tokens: Optional[int] = SESSION_CONTEXT_WINDOW_MAX_TOKENS,
        redis_host: str = SEMANTIC_CACHE_REDIS_HOST,
        redis_port: int = SEMANTIC_CACHE_REDIS_PORT,
        redis_db: int = SESSION_CONTEXT_WINDOW_REDIS_DB
    ):
        self.session_id = session_id
        self.window_size = window_size
        self.ttl_seconds = ttl_seconds
        self.max_tokens = max_tokens
        self.redis_client = None
        self.lock = threading.RLock()
        
        if not REDIS_AVAILABLE:
            raise RuntimeError("[semanticCacheRedis.SessionContextWindow] Redis is required but not installed")
        
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True,
                socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
                socket_keepalive=REDIS_SOCKET_KEEPALIVE
            )
            self.redis_client.ping()
            logger.info(
                f"[semanticCacheRedis.SessionContextWindow] session={session_id} initialized: "
                f"window_size={window_size}, ttl={ttl_seconds}s, max_tokens={max_tokens}"
            )
        except Exception as e:
            logger.error(f"[semanticCacheRedis.SessionContextWindow] session={session_id} Failed to connect: {e}")
            raise
    
    def _get_key(self) -> str:
        """Redis hash key for session messages"""
        return f"{REDIS_KEY_PREFIX}:session_context:{self.session_id}"
    
    def _get_order_key(self) -> str:
        """Redis list key for message ordering (LRU)"""
        return f"{REDIS_KEY_PREFIX}:session_order:{self.session_id}"
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> int:
        """Add message to context window. Returns current window size."""
        with self.lock:
            try:
                key = self._get_key()
                order_key = self._get_order_key()
                timestamp = time.time()
                
                msg_id = int(timestamp * 1000) % (2**31)
                message = {
                    "role": role,
                    "content": content,
                    "timestamp": timestamp,
                    "metadata": metadata or {}
                }
                
                msg_key = f"{key}:{msg_id}"
                self.redis_client.setex(
                    msg_key,
                    self.ttl_seconds,
                    pickle.dumps(message)
                )
                
                self.redis_client.lpush(order_key, msg_id)
                self.redis_client.expire(order_key, self.ttl_seconds)
                
                window_len = self.redis_client.llen(order_key)
                if window_len > self.window_size:
                    excess = window_len - self.window_size
                    for _ in range(excess):
                        old_id = self.redis_client.rpop(order_key)
                        if old_id:
                            self.redis_client.delete(f"{key}:{old_id}")
                            logger.debug(f"[semanticCacheRedis.SessionContextWindow] session={self.session_id} LRU evicted {old_id}")
                
                logger.debug(f"[semanticCacheRedis.SessionContextWindow] session={self.session_id} Added {role} (window: {min(window_len, self.window_size)}/{self.window_size})")
                return min(window_len, self.window_size)
                
            except Exception as e:
                logger.warning(f"[semanticCacheRedis.SessionContextWindow] session={self.session_id} Failed to add message: {e}")
                return 0
    
    def get_context(self) -> List[Dict]:
        """Retrieve all messages in context window (in chronological order)"""
        with self.lock:
            try:
                key = self._get_key()
                order_key = self._get_order_key()
                
                msg_ids = self.redis_client.lrange(order_key, 0, -1)
                
                messages = []
                for msg_id in reversed(msg_ids):
                    try:
                        msg_key = f"{key}:{msg_id}"
                        msg_data = self.redis_client.get(msg_key)
                        if msg_data:
                            message = pickle.loads(msg_data)
                            messages.append(message)
                    except Exception as e:
                        logger.warning(f"[semanticCacheRedis.SessionContextWindow] session={self.session_id} Failed to decode {msg_id}: {e}")
                
                logger.debug(f"[semanticCacheRedis.SessionContextWindow] session={self.session_id} Retrieved {len(messages)} messages")
                return messages
            except Exception as e:
                logger.warning(f"[semanticCacheRedis.SessionContextWindow] session={self.session_id} Failed to get context: {e}")
                return []
    
    def get_formatted_context(self, max_lines: int = 50) -> str:
        """Get formatted context for display/logging"""
        messages = self.get_context()
        lines = []
        
        for msg in messages:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            if content:
                if len(content) > 200:
                    content = content[:200] + "..."
                lines.append(f"{role}: {content}")
        
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        
        return "\n".join(lines) if lines else ""
    
    def clear(self) -> bool:
        """Clear all messages for this session"""
        with self.lock:
            try:
                key = self._get_key()
                order_key = self._get_order_key()
                
                msg_ids = self.redis_client.lrange(order_key, 0, -1)
                
                for msg_id in msg_ids:
                    self.redis_client.delete(f"{key}:{msg_id}")
                
                self.redis_client.delete(order_key)
                
                logger.info(f"[semanticCacheRedis.SessionContextWindow] session={self.session_id} Cleared {len(msg_ids)} messages")
                return True
            except Exception as e:
                logger.warning(f"[semanticCacheRedis.SessionContextWindow] session={self.session_id} Failed to clear: {e}")
                return False
    
    def get_stats(self) -> Dict:
        """Get usage statistics for this session"""
        try:
            order_key = self._get_order_key()
            window_len = self.redis_client.llen(order_key)
            
            return {
                "session_id": self.session_id,
                "messages_in_window": window_len,
                "window_size": self.window_size,
                "utilization": window_len / self.window_size if self.window_size > 0 else 0,
                "ttl_seconds": self.ttl_seconds,
                "max_tokens": self.max_tokens
            }
        except Exception as e:
            logger.warning(f"[semanticCacheRedis.SessionContextWindow] session={self.session_id} Failed to get stats: {e}")
            return {"session_id": self.session_id, "status": "error"}


class SemanticCacheRedis:
    """
    Semantic query cache per sessionID (short-lived, 5min TTL).
    Stores URL + query_embedding → retrieval results.
    Key format: semantic_cache:SESSION_ID:URL
    Ensures each session can scale independently.
    Default: Redis DB 0, TTL 300s, similarity 0.90, max 50 queries/URL
    """
    
    def __init__(
        self, 
        session_id: str,
        ttl_seconds: int = SEMANTIC_CACHE_REDIS_TTL_SECONDS, 
        similarity_threshold: float = SEMANTIC_CACHE_REDIS_SIMILARITY_THRESHOLD,
        max_items_per_url: int = SEMANTIC_CACHE_REDIS_MAX_ITEMS_PER_URL,
        redis_host: str = SEMANTIC_CACHE_REDIS_HOST,
        redis_port: int = SEMANTIC_CACHE_REDIS_PORT,
        redis_db: int = SEMANTIC_CACHE_REDIS_DB
    ):
        self.session_id = session_id
        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold
        self.max_items_per_url = max_items_per_url
        self.redis_client = None
        self.lock = threading.RLock()
        
        if not REDIS_AVAILABLE:
            logger.error("[semanticCacheRedis.SemanticCacheRedis] Redis is REQUIRED but not installed")
            raise RuntimeError("Redis installation is required for semantic caching")
        
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=False,
                socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
                socket_keepalive=REDIS_SOCKET_KEEPALIVE
            )
            self.redis_client.ping()
            logger.info(
                f"[semanticCacheRedis.SemanticCacheRedis] session={session_id} connected to Redis @ "
                f"{redis_host}:{redis_port} (db={redis_db}, ttl={ttl_seconds}s, threshold={similarity_threshold})"
            )
        except Exception as e:
            logger.error(f"[semanticCacheRedis.SemanticCacheRedis] session={session_id} Failed to connect: {e}")
            raise
    
    def _get_redis_key(self, url: str) -> str:
        """Redis key: semantic_cache:SESSION_ID:URL"""
        return f"{REDIS_KEY_PREFIX}:semantic_cache:{self.session_id}:{url}"
    
    def get(self, url: str, query_embedding: np.ndarray) -> Optional[Dict]:
        """
        Get cached semantic response for URL + query.
        Returns closest matching response if similarity >= threshold.
        """
        with self.lock:
            try:
                redis_key = self._get_redis_key(url)
                cached_data = self.redis_client.get(redis_key)
                
                if not cached_data:
                    logger.debug(f"[semanticCacheRedis.SemanticCacheRedis] session={self.session_id} MISS: {url}")
                    return None
                
                cache_entry = pickle.loads(cached_data)
                best_match = None
                best_similarity = 0.0
                
                query_emb = np.array(query_embedding, dtype=np.float32)
                query_emb = query_emb / (np.linalg.norm(query_emb) + 1e-8)
                
                for cached_item in cache_entry.get("items", []):
                    cached_emb = np.array(cached_item["embedding"], dtype=np.float32)
                    cached_emb = cached_emb / (np.linalg.norm(cached_emb) + 1e-8)
                    similarity = float(np.dot(cached_emb, query_emb))
                    
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = cached_item
                
                if best_similarity >= self.similarity_threshold and best_match:
                    logger.debug(f"[semanticCacheRedis.SemanticCacheRedis] session={self.session_id} HIT: {url} (similarity: {best_similarity:.3f})")
                    return best_match["response"]
                
                logger.debug(f"[semanticCacheRedis.SemanticCacheRedis] session={self.session_id} LOW SIMILARITY: {url} ({best_similarity:.3f} < {self.similarity_threshold})")
                return None
            except Exception as e:
                logger.warning(f"[semanticCacheRedis.SemanticCacheRedis] session={self.session_id} Get error for {url}: {e}")
                return None
    
    def set(self, url: str, query_embedding: np.ndarray, response: Dict) -> None:
        """
        Store semantic response for URL + query embedding.
        Maintains max_items_per_url recent queries.
        """
        with self.lock:
            try:
                redis_key = self._get_redis_key(url)
                
                cached_data = self.redis_client.get(redis_key)
                if cached_data:
                    cache_entry = pickle.loads(cached_data)
                else:
                    cache_entry = {"items": []}
                
                cache_entry["items"].append({
                    "embedding": query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding,
                    "response": response,
                    "timestamp": time.time()
                })
                
                if len(cache_entry["items"]) > self.max_items_per_url:
                    cache_entry["items"] = cache_entry["items"][-self.max_items_per_url:]
                
                self.redis_client.setex(
                    redis_key,
                    self.ttl_seconds,
                    pickle.dumps(cache_entry)
                )
                logger.debug(f"[semanticCacheRedis.SemanticCacheRedis] session={self.session_id} STORED: {url} ({len(cache_entry['items'])}/{self.max_items_per_url})")
            except Exception as e:
                logger.warning(f"[semanticCacheRedis.SemanticCacheRedis] session={self.session_id} Set error: {e}")
    
    def clear_session(self) -> bool:
        """Clear all semantic cache entries for this session"""
        with self.lock:
            try:
                pattern = f"{REDIS_KEY_PREFIX}:semantic_cache:{self.session_id}:*"
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
                    logger.info(f"[semanticCacheRedis.SemanticCacheRedis] session={self.session_id} Cleared {len(keys)} entries")
                return True
            except Exception as e:
                logger.warning(f"[semanticCacheRedis.SemanticCacheRedis] session={self.session_id} Failed to clear: {e}")
                return False
    
    def get_stats(self) -> Dict:
        """Get cache statistics for this session"""
        try:
            info = self.redis_client.info("memory")
            pattern = f"{REDIS_KEY_PREFIX}:semantic_cache:{self.session_id}:*"
            keys = self.redis_client.keys(pattern)
            
            return {
                "backend": "redis",
                "session_id": self.session_id,
                "cached_urls": len(keys),
                "redis_memory_used": info.get("used_memory_human", "unknown"),
                "ttl_seconds": self.ttl_seconds,
                "similarity_threshold": self.similarity_threshold,
                "max_items_per_url": self.max_items_per_url
            }
        except Exception as e:
            logger.warning(f"[semanticCacheRedis.SemanticCacheRedis] session={self.session_id} Failed to get stats: {e}")
            return {"session_id": self.session_id, "status": "error"}


# Backwards compatibility alias
