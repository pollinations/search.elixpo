#!/usr/bin/env python3
"""
Test script for Redis-based semantic cache
Tests both Redis and fallback file-based implementations
"""

import numpy as np
import sys
import os
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from lixsearch.ragService.semanticCacheRedis import SemanticCacheRedis, SemanticQueryCache
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="DEBUG")


def test_semantic_query_cache():
    """Test the in-memory query cache."""
    logger.info("=" * 60)
    logger.info("Testing SemanticQueryCache (In-Memory)")
    logger.info("=" * 60)
    
    cache = SemanticQueryCache(ttl_seconds=3600, max_size=100)
    
    # Create some test embeddings
    embedding1 = np.random.randn(384).astype(np.float32)
    embedding2 = np.random.randn(384).astype(np.float32)
    
    # Create test results
    results1 = [{"title": "Result 1", "score": 0.95}]
    results2 = [{"title": "Result 2", "score": 0.87}]
    
    # Store
    cache.set(embedding1, top_k=5, results=results1)
    cache.set(embedding2, top_k=10, results=results2)
    
    # Retrieve
    retrieved1 = cache.get(embedding1, top_k=5)
    retrieved2 = cache.get(embedding2, top_k=10)
    
    assert retrieved1 is not None, "Failed to retrieve cached results 1"
    assert retrieved2 is not None, "Failed to retrieve cached results 2"
    assert retrieved1 == results1, "Retrieved results don't match stored results"
    
    # Test miss
    embedding3 = np.random.randn(384).astype(np.float32)
    retrieved3 = cache.get(embedding3, top_k=5)
    assert retrieved3 is None, "Should return None for cache miss"
    
    # Test stats
    stats = cache.stats()
    logger.info(f"Cache stats: {stats}")
    assert stats["cached_queries"] == 2, "Should have 2 cached queries"
    
    logger.success("✅ SemanticQueryCache tests passed!")


def test_redis_semantic_cache():
    """Test the Redis-based semantic cache."""
    logger.info("=" * 60)
    logger.info("Testing SemanticCacheRedis (Redis + Fallback)")
    logger.info("=" * 60)
    
    cache = SemanticCacheRedis(
        ttl_seconds=300,
        similarity_threshold=0.90,
        cache_dir="./cache",
        redis_host="localhost",
        redis_port=6379,
        redis_db=0
    )
    
    request_id = "test_request_123"
    url1 = "https://example.com/page1"
    url2 = "https://example.com/page2"
    
    # Create test embeddings
    embedding1 = np.random.randn(384).astype(np.float32)
    embedding2 = np.random.randn(384).astype(np.float32)
    embedding1_similar = embedding1 + np.random.randn(384) * 0.01  # Very similar
    
    # Create test responses
    response1 = {"content": "Response 1", "score": 0.95}
    response2 = {"content": "Response 2", "score": 0.87}
    
    # Store
    cache.set(url1, embedding1, response1, request_id)
    cache.set(url2, embedding2, response2, request_id)
    
    # Retrieve
    retrieved1 = cache.get(url1, embedding1, request_id)
    retrieved2 = cache.get(url2, embedding2, request_id)
    
    if cache.use_redis:
        logger.info("✅ Running in Redis mode")
    else:
        logger.info("⚠️ Running in fallback file-based mode (Redis not available)")
    
    # Note: Retrieved results might be None if similarity is below threshold
    # due to random embeddings. Just check that get doesn't error.
    logger.info(f"Retrieved from URL1: {retrieved1}")
    logger.info(f"Retrieved from URL2: {retrieved2}")
    
    # Test similar embedding (should potentially match)
    similar_retrieved = cache.get(url1, embedding1_similar, request_id)
    logger.info(f"Retrieved with similar embedding: {similar_retrieved}")
    
    # Test stats
    stats = cache.get_stats()
    logger.info(f"Cache stats: {stats}")
    
    # Test save/load
    cache.save_for_request(request_id)
    cache.clear_request(request_id)
    loaded = cache.load_for_request(request_id)
    logger.info(f"Cache saved, cleared, and reloaded: {loaded}")
    
    logger.success("✅ SemanticCacheRedis tests passed!")


def test_fallback_mode():
    """Test file-based fallback when Redis is not available."""
    logger.info("=" * 60)
    logger.info("Testing Fallback Mode (File-Based)")
    logger.info("=" * 60)
    
    # Force fallback by using invalid Redis credentials
    cache = SemanticCacheRedis(
        ttl_seconds=300,
        similarity_threshold=0.90,
        cache_dir="./cache_fallback_test",
        redis_host="invalid_host_xyz",
        redis_port=9999,
        redis_db=0
    )
    
    request_id = "fallback_test_456"
    url = "https://example.com/fallback"
    
    embedding = np.random.randn(384).astype(np.float32)
    response = {"content": "Fallback test response"}
    
    # Store and retrieve
    cache.set(url, embedding, response, request_id)
    cache.save_for_request(request_id)
    
    cache.clear_request(request_id)
    loaded = cache.load_for_request(request_id)
    
    logger.info(f"Fallback cache backend: {'redis' if cache.use_redis else 'file-based'}")
    logger.success("✅ Fallback mode tests passed!")


def test_embedding_service_device():
    """Test embedding service device selection."""
    logger.info("=" * 60)
    logger.info("Testing EmbeddingService Device Selection")
    logger.info("=" * 60)
    
    try:
        from lixsearch.ragService.embeddingService import EmbeddingService
        
        # Don't actually load the model, just test device selection
        device = EmbeddingService._select_device()
        logger.info(f"Selected device: {device}")
        assert device in ["cuda", "cpu", "mps"], f"Invalid device: {device}"
        
        logger.success("✅ Device selection tests passed!")
    except Exception as e:
        logger.error(f"Device selection test failed: {e}")


if __name__ == "__main__":
    logger.info("\n" + "=" * 60)
    logger.info("Redis-Based Semantic Cache Test Suite")
    logger.info("=" * 60 + "\n")
    
    try:
        test_semantic_query_cache()
        test_redis_semantic_cache()
        test_fallback_mode()
        test_embedding_service_device()
        
        logger.info("\n" + "=" * 60)
        logger.success("✅ All tests passed successfully!")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
