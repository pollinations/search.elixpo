"""
Cache Coordinator: Orchestrates multiple Redis caches for optimal performance.

Manages interactions between:
1. URLEmbeddingCache - caches URL embeddings (24h TTL)
2. SemanticCacheRedis - caches semantic query responses (5m TTL)
3. SessionContextWindow - manages conversation history (1h TTL, LRU eviction)

Key Design:
- Single embedding per URL (cached for 24h) - reused across all queries
- Semantic response cache (5m) for repeated queries on same URL
- Session message window (configurable size, default 20 messages) with LRU
- Redis-only, no file storage for speed
"""

from typing import Dict, Optional, Tuple
from loguru import logger
import numpy as np
from datetime import datetime

from ragService.semanticCacheRedis import (
    URLEmbeddingCache,
    SemanticCacheRedis,
    SessionContextWindow
)


class CacheCoordinator:
    """
    Coordinates caching across URL embeddings, semantic responses, and session context.
    """
    
    def __init__(
        self,
        session_id: str,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        context_window_size: int = 20,
        context_window_ttl_seconds: int = 3600,
    ):
        self.session_id = session_id
        
        try:
            # Initialize three separate Redis caches with different DBs
            self.url_embedding_cache = URLEmbeddingCache(
                ttl_seconds=86400,  # 24 hours for URL embeddings
                redis_host=redis_host,
                redis_port=redis_port,
                redis_db=1
            )
            
            self.semantic_cache = SemanticCacheRedis(
                ttl_seconds=300,  # 5 minutes for semantic responses
                similarity_threshold=0.90,
                redis_host=redis_host,
                redis_port=redis_port,
                redis_db=0
            )
            
            self.context_window = SessionContextWindow(
                session_id=session_id,
                window_size=context_window_size,
                ttl_seconds=context_window_ttl_seconds,
                redis_host=redis_host,
                redis_port=redis_port,
                redis_db=2
            )
            
            logger.info(
                f"[CacheCoordinator] Initialized for session {session_id}: "
                f"context_window={context_window_size}, ttl={context_window_ttl_seconds}s"
            )
        except Exception as e:
            logger.error(f"[CacheCoordinator] Initialization failed: {e}")
            raise
    
    def get_url_embedding(self, url: str) -> Optional[np.ndarray]:
        """Get cached embedding for URL (if exists)."""
        return self.url_embedding_cache.get(url)
    
    def cache_url_embedding(self, url: str, embedding: np.ndarray) -> bool:
        """Cache embedding for URL."""
        return self.url_embedding_cache.set(url, embedding)
    
    def get_semantic_response(
        self,
        url: str,
        query_embedding: np.ndarray
    ) -> Optional[Dict]:
        """Get cached semantic response for URL + query."""
        return self.semantic_cache.get(
            url=url,
            query_embedding=query_embedding,
            request_id=self.session_id
        )
    
    def cache_semantic_response(
        self,
        url: str,
        query_embedding: np.ndarray,
        response: Dict
    ) -> None:
        """Cache semantic response for URL + query."""
        self.semantic_cache.set(
            url=url,
            query_embedding=query_embedding,
            response=response,
            request_id=self.session_id
        )
    
    def add_message_to_context(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> int:
        """Add message to session context window. Returns window size."""
        return self.context_window.add_message(role, content, metadata)
    
    def get_context_messages(self) -> list:
        """Get all messages in current context window."""
        return self.context_window.get_context()
    
    def get_formatted_context(self, max_lines: int = 50) -> str:
        """Get formatted context for prompt engineering."""
        return self.context_window.get_formatted_context(max_lines)
    
    def clear_context(self) -> bool:
        """Clear session context window."""
        return self.context_window.clear()
    
    def get_cache_stats(self) -> Dict:
        """Get statistics for all caches."""
        return {
            "session_id": self.session_id,
            "url_embedding_cache": self.url_embedding_cache.get_stats(),
            "semantic_cache": self.semantic_cache.get_stats(),
            "context_window": self.context_window.get_stats(),
            "timestamp": datetime.now().isoformat()
        }


class BatchCacheProcessor:
    """
    Batch processor for caching multiple URL embeddings efficiently.
    """
    
    def __init__(self, url_embedding_cache: URLEmbeddingCache):
        self.cache = url_embedding_cache
    
    def cache_batch(self, url_embedding_pairs: list) -> Dict:
        """
        Cache multiple URL-embedding pairs.
        
        Args:
            url_embedding_pairs: List of (url: str, embedding: np.ndarray) tuples
        
        Returns:
            Dict with success/failure counts
        """
        stats = {
            "total": len(url_embedding_pairs),
            "cached": 0,
            "failed": 0,
            "urls": []
        }
        
        for url, embedding in url_embedding_pairs:
            try:
                if self.cache.set(url, embedding):
                    stats["cached"] += 1
                else:
                    stats["failed"] += 1
                stats["urls"].append(url)
            except Exception as e:
                logger.warning(f"[BatchCacheProcessor] Failed to cache {url}: {e}")
                stats["failed"] += 1
        
        logger.info(
            f"[BatchCacheProcessor] Batch complete: "
            f"{stats['cached']} cached, {stats['failed']} failed"
        )
        return stats
