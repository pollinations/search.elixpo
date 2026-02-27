"""
IPC Client for CoreEmbeddingService
Provides a transparent proxy to the shared embedding service running on IPC port 5010
"""
from loguru import logger
from multiprocessing.managers import BaseManager
from typing import Union, List, Optional
import numpy as np
import threading
from pipeline.config import IPC_HOST, IPC_PORT, IPC_AUTHKEY, IPC_TIMEOUT


class ModelServerClient(BaseManager):
    """BaseManager for IPC connection to embedding service"""
    pass


ModelServerClient.register('CoreEmbeddingService')


class EmbeddingServiceClient:
    """
    Transparent client that connects to the shared CoreEmbeddingService
    via IPC and delegates all embedding operations to it.
    
    This allows multiple workers to share a single embedding model instance,
    reducing memory usage and avoiding duplicate model loads.
    """
    _instance = None
    _lock = threading.Lock()
    _connection_lock = threading.Lock()
    
    def __init__(self, max_retries: int = 3, timeout: float = IPC_TIMEOUT):
        self.host = IPC_HOST
        self.port = IPC_PORT
        self.authkey = IPC_AUTHKEY
        self.timeout = timeout
        self.max_retries = max_retries
        self.device = "ipc-remote"  # Virtual device indicating remote execution
        self._core_service = None
        self._manager = None
        self._connect()
    
    @classmethod
    def get_instance(cls, max_retries: int = 3, timeout: float = IPC_TIMEOUT):
        """Singleton pattern with lazy initialization"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = EmbeddingServiceClient(max_retries=max_retries, timeout=timeout)
        return cls._instance
    
    def _connect(self) -> None:
        """Establish connection to IPC server with retries"""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                with self._connection_lock:
                    logger.info(
                        f"[EmbeddingServiceClient] Connecting to IPC server "
                        f"{self.host}:{self.port} (attempt {attempt + 1}/{self.max_retries})"
                    )
                    
                    self._manager = ModelServerClient(
                        address=(self.host, self.port),
                        authkey=self.authkey
                    )
                    self._manager.connect()
                    self._core_service = self._manager.CoreEmbeddingService()
                    
                    # Verify connection with a dummy call
                    stats = self._core_service.get_vector_store_stats()
                    logger.info(
                        f"[EmbeddingServiceClient] ✅ Connected to CoreEmbeddingService at "
                        f"{self.host}:{self.port}. Vector store chunks: {stats.get('chunk_count', 0)}"
                    )
                    return
                    
            except Exception as e:
                last_error = e
                logger.warning(
                    f"[EmbeddingServiceClient] Connection attempt {attempt + 1} failed: {e}"
                )
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff
        
        logger.error(
            f"[EmbeddingServiceClient] Failed to connect to IPC service after "
            f"{self.max_retries} attempts. Last error: {last_error}"
        )
        raise RuntimeError(
            f"Cannot connect to CoreEmbeddingService at {self.host}:{self.port}. "
            f"Make sure the IPC service is running."
        ) from last_error
    
    def embed(self, texts: Union[str, List[str]], batch_size: int = 32) -> np.ndarray:
        """
        Get embeddings for texts via IPC call to CoreEmbeddingService
        
        Args:
            texts: Single text string or list of texts
            batch_size: Batch size for processing
            
        Returns:
            numpy array of embeddings
        """
        try:
            with self._connection_lock:
                # Convert to list if needed
                if isinstance(texts, str):
                    texts = [texts]
                
                logger.debug(f"[EmbeddingServiceClient] Embedding {len(texts)} texts (batch_size={batch_size})")
                
                # Call IPC service
                embeddings = self._core_service.embed_batch(texts, batch_size=batch_size)
                
                # Convert back to numpy array if needed
                if isinstance(embeddings, list):
                    embeddings = np.array(embeddings, dtype=np.float32)
                
                logger.debug(f"[EmbeddingServiceClient] Embeddings shape: {embeddings.shape}")
                return embeddings
                
        except Exception as e:
            logger.error(f"[EmbeddingServiceClient] Embedding failed: {e}")
            raise
    
    def embed_single(self, text: str) -> np.ndarray:
        """
        Get embedding for a single text via IPC call to CoreEmbeddingService
        
        Args:
            text: Single text string
            
        Returns:
            numpy array of embedding
        """
        try:
            with self._connection_lock:
                logger.debug(f"[EmbeddingServiceClient] Embedding single text")
                
                # Call IPC service
                embedding = self._core_service.embed_single_text(text)
                
                # Convert to numpy array if needed
                if isinstance(embedding, list):
                    embedding = np.array(embedding, dtype=np.float32)
                
                logger.debug(f"[EmbeddingServiceClient] Single embedding shape: {embedding.shape}")
                return embedding
                
        except Exception as e:
            logger.error(f"[EmbeddingServiceClient] Single embedding failed: {e}")
            raise
    
    def get_vector_store_stats(self) -> dict:
        """Get vector store statistics from the IPC service"""
        try:
            with self._connection_lock:
                return self._core_service.get_vector_store_stats()
        except Exception as e:
            logger.error(f"[EmbeddingServiceClient] Failed to get vector store stats: {e}")
            return {"error": str(e)}
    
    def get_semantic_cache_stats(self) -> dict:
        """Get semantic cache statistics from the IPC service"""
        try:
            with self._connection_lock:
                return self._core_service.get_semantic_cache_stats()
        except Exception as e:
            logger.error(f"[EmbeddingServiceClient] Failed to get cache stats: {e}")
            return {"error": str(e)}
    
    def health_check(self) -> bool:
        """Check if IPC service is healthy"""
        try:
            with self._connection_lock:
                stats = self._core_service.get_vector_store_stats()
                return stats is not None
        except Exception as e:
            logger.warning(f"[EmbeddingServiceClient] Health check failed: {e}")
            return False
    
    def disconnect(self) -> None:
        """Gracefully disconnect from IPC service"""
        try:
            if self._manager:
                self._manager.shutdown()
                logger.info("[EmbeddingServiceClient] Disconnected from IPC service")
        except Exception as e:
            logger.warning(f"[EmbeddingServiceClient] Disconnect error: {e}")
