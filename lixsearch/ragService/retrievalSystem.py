import threading
from loguru import logger
import numpy as np
from typing import Dict, List
from ragService.embeddingService import EmbeddingService
from ragService.vectorStore import VectorStore
from ragService.ragEngine import RAGEngine
from ragService.semanticCacheRedis import SemanticCacheRedis as SemanticCache
from sessions.main import get_session_manager

_retrieval_system = None

from pipeline.config import (
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    EMBEDDINGS_DIR,
    SEMANTIC_CACHE_DIR,
    SEMANTIC_CACHE_TTL_SECONDS,
    SEMANTIC_CACHE_SIMILARITY_THRESHOLD,
    REDIS_URL
)


class RetrievalSystem:
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = RetrievalSystem()
        return cls._instance
    
    def __init__(self):
        logger.info("[RetrievalSystem] Initializing...")
        self.embedding_service = EmbeddingService(model_name=EMBEDDING_MODEL)
        logger.info(f"[RetrievalSystem] Embedding service device: {self.embedding_service.device}")
        
        self.vector_store = VectorStore(embedding_dim=EMBEDDING_DIMENSION, embeddings_dir=EMBEDDINGS_DIR)
        logger.info(f"[RetrievalSystem] Vector store device: {self.vector_store.device}")
        
        # Parse Redis URL for semantic cache initialization
        redis_host = "localhost"
        redis_port = 6379
        redis_db = 0
        if REDIS_URL:
            # Parse format: redis://host:port/db
            try:
                url_parts = REDIS_URL.replace("redis://", "").split("/")
                host_port = url_parts[0].split(":")
                redis_host = host_port[0]
                redis_port = int(host_port[1]) if len(host_port) > 1 else 6379
                redis_db = int(url_parts[1]) if len(url_parts) > 1 else 0
            except Exception as e:
                logger.warning(f"[RetrievalSystem] Failed to parse REDIS_URL, using defaults: {e}")
        
        self.semantic_cache = SemanticCache(
            session_id="global",
            ttl_seconds=SEMANTIC_CACHE_TTL_SECONDS,
            similarity_threshold=SEMANTIC_CACHE_SIMILARITY_THRESHOLD,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db
        )
        logger.info(f"[RetrievalSystem] Semantic cache: TTL={SEMANTIC_CACHE_TTL_SECONDS}s, threshold={SEMANTIC_CACHE_SIMILARITY_THRESHOLD}, redis={redis_host}:{redis_port}/{redis_db}")
        
        self.sessions_lock = threading.RLock()
        
        logger.info("[RetrievalSystem] ✅ Fully initialized with GPU acceleration")
    
    def create_session(self, session_id: str):
        logger.warning(f"[RetrievalSystem] Deprecated create_session() called for {session_id}. Use SessionManager instead.")
        return None
    
    def get_session(self, session_id: str):
        return None
    
    def get_rag_engine(self, session_id: str) -> RAGEngine:
        session_manager = get_session_manager()
        session_data = session_manager.get_session(session_id)
        
        if not session_data:
            logger.warning(f"[RetrievalSystem] Session {session_id} not found in SessionManager")
            session_data = session_manager.get_session(session_id) or type('SessionData', (), {'get_conversation_history': lambda: [], 'to_dict': lambda: {}})()
        
        return RAGEngine(
            self.embedding_service,
            self.vector_store,
            self.semantic_cache,
            session_data
        )
    
    def add_conversation_turn(
        self,
        session_id: str,
        user_query: str,
        assistant_response: str,
        entities: List[str] = None
    ) -> None:
        session_manager = get_session_manager()
        session_manager.add_message_to_history(
            session_id,
            "user",
            user_query
        )
        session_manager.add_message_to_history(
            session_id,
            "assistant",
            assistant_response,
            metadata={"entities": entities} if entities else None
        )
    
    def delete_session(self, session_id: str) -> None:
        session_manager = get_session_manager()
        session_manager.cleanup_session(session_id)
        logger.info(f"[RetrievalSystem] Deleted session {session_id}")
    
    def get_stats(self) -> Dict:
        session_manager = get_session_manager()
        sessions_stats = session_manager.get_stats()
        
        return {
            "vector_store": self.vector_store.get_stats(),
            "semantic_cache": self.semantic_cache.get_stats(),
            "active_sessions": sessions_stats.get("total_sessions", 0)
        }
    
    def persist_vector_store(self) -> None:
        self.vector_store.persist_to_disk()



