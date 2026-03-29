"""Vector store factory for creating appropriate vector store instances.

This module provides factory functions to create vector store instances
based on configuration and environment requirements.
"""

import os
from typing import Union, Optional
from config.settings import Settings
from utils.logger import get_logger
from .vector_store import InMemoryVectorStore, ChromaVectorStore


logger = get_logger(__name__)


def create_vector_store(
    config: Optional[Settings] = None,
    store_type: Optional[str] = None,
    **kwargs
) -> Union[InMemoryVectorStore, ChromaVectorStore]:
    """Create appropriate vector store instance based on configuration.
    
    Args:
        config: Settings instance. If None, creates new instance.
        store_type: Override store type ('inmemory' or 'chroma').
        **kwargs: Additional arguments passed to vector store constructor.
        
    Returns:
        Vector store instance.
        
    Raises:
        ValueError: If store type is invalid or configuration is missing.
    """
    if config is None:
        config = Settings()
    
    # Determine store type
    if store_type is None:
        store_type = config.get('duplicate_detection', 'vector_store_type', fallback='inmemory')
    
    store_type = store_type.lower()
    
    if store_type == 'inmemory':
        return _create_inmemory_store(config, **kwargs)
    elif store_type == 'chroma':
        return _create_chroma_store(config, **kwargs)
    else:
        raise ValueError(f"Unsupported vector store type: {store_type}")


def _create_inmemory_store(config: Settings, **kwargs) -> InMemoryVectorStore:
    """Create InMemoryVectorStore instance.
    
    Args:
        config: Settings instance.
        **kwargs: Additional constructor arguments.
        
    Returns:
        InMemoryVectorStore instance.
    """
    embedding_dimension = kwargs.get(
        'embedding_dimension',
        config.get_int('duplicate_detection', 'embedding_dimension', fallback=384)
    )
    
    logger.info(f"Creating InMemoryVectorStore with dimension {embedding_dimension}")
    
    return InMemoryVectorStore(
        embedding_dimension=embedding_dimension,
        **kwargs
    )


def _create_chroma_store(config: Settings, **kwargs) -> ChromaVectorStore:
    """Create ChromaVectorStore instance.
    
    Args:
        config: Settings instance.
        **kwargs: Additional constructor arguments.
        
    Returns:
        ChromaVectorStore instance.
        
    Raises:
        ValueError: If required Chroma configuration is missing.
    """
    # Get Chroma configuration
    persist_directory = kwargs.get(
        'persist_directory',
        config.get('chroma', 'persist_directory', fallback='./data/chroma_db')
    )
    
    collection_name = kwargs.get(
        'collection_name',
        config.get('chroma', 'collection_name', fallback='company_embeddings')
    )
    
    embedding_model = kwargs.get(
        'embedding_model',
        config.get('chroma', 'embedding_model', fallback='sentence-transformers/all-MiniLM-L6-v2')
    )
    
    embedding_dimension = kwargs.get(
        'embedding_dimension',
        config.get_int('chroma', 'embedding_dimension', fallback=384)
    )
    
    distance_function = kwargs.get(
        'distance_function',
        config.get('chroma', 'distance_function', fallback='cosine')
    )
    
    # Validate configuration
    if not persist_directory:
        raise ValueError("Chroma persist_directory is required")
    
    if not collection_name:
        raise ValueError("Chroma collection_name is required")
    
    logger.info(
        f"Creating ChromaVectorStore: collection='{collection_name}', "
        f"model='{embedding_model}', directory='{persist_directory}'"
    )
    
    return ChromaVectorStore(
        persist_directory=persist_directory,
        collection_name=collection_name,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        distance_function=distance_function
    )


def get_default_vector_store() -> Union[InMemoryVectorStore, ChromaVectorStore]:
    """Get default vector store instance based on environment.
    
    Returns:
        Default vector store instance.
    """
    config = Settings()
    
    # Use Chroma in production, InMemory for development/testing
    if config.is_production:
        store_type = 'chroma'
    else:
        store_type = config.get('duplicate_detection', 'vector_store_type', fallback='inmemory')
    
    return create_vector_store(config=config, store_type=store_type)


def create_test_vector_store(
    store_type: str = 'inmemory',
    embedding_dimension: int = 384
) -> Union[InMemoryVectorStore, ChromaVectorStore]:
    """Create vector store instance for testing.
    
    Args:
        store_type: Type of store to create ('inmemory' or 'chroma').
        embedding_dimension: Embedding vector dimension.
        
    Returns:
        Vector store instance configured for testing.
    """
    if store_type == 'inmemory':
        return InMemoryVectorStore(embedding_dimension=embedding_dimension)
    elif store_type == 'chroma':
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix='test_chroma_')
        return ChromaVectorStore(
            persist_directory=temp_dir,
            collection_name='test_collection',
            embedding_dimension=embedding_dimension
        )
    else:
        raise ValueError(f"Unsupported test store type: {store_type}")


def validate_vector_store_config(config: Settings) -> bool:
    """Validate vector store configuration.
    
    Args:
        config: Settings instance to validate.
        
    Returns:
        True if configuration is valid, False otherwise.
    """
    try:
        store_type = config.get('duplicate_detection', 'vector_store_type', fallback='inmemory')
        
        if store_type == 'chroma':
            # Validate Chroma-specific configuration
            persist_directory = config.get('chroma', 'persist_directory')
            collection_name = config.get('chroma', 'collection_name')
            embedding_model = config.get('chroma', 'embedding_model')
            
            if not persist_directory:
                logger.error("Chroma persist_directory not configured")
                return False
            
            if not collection_name:
                logger.error("Chroma collection_name not configured")
                return False
            
            if not embedding_model:
                logger.error("Chroma embedding_model not configured")
                return False
            
            # Check if directory is writable
            try:
                os.makedirs(persist_directory, exist_ok=True)
                test_file = os.path.join(persist_directory, '.test_write')
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
            except Exception as e:
                logger.error(f"Chroma persist_directory not writable: {e}")
                return False
        
        # Validate common configuration
        embedding_dimension = config.get_int('duplicate_detection', 'embedding_dimension', fallback=384)
        if embedding_dimension <= 0:
            logger.error("Invalid embedding_dimension")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Vector store configuration validation failed: {e}")
        return False