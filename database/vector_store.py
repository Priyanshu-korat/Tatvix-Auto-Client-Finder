"""Vector store protocol and implementations for duplicate detection.

This module provides the VectorStore protocol for embedding-based similarity
detection and includes both in-memory and Chroma implementations.
"""

import logging
import numpy as np
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, Protocol
from datetime import datetime
from dataclasses import dataclass

from utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class EmbeddingRecord:
    """Record for storing company embeddings."""
    
    company_id: str
    domain: str
    embedding: np.ndarray
    metadata: Dict[str, Any]
    created_at: datetime
    
    def __post_init__(self) -> None:
        """Validate embedding record after initialization."""
        if not self.company_id or not self.domain:
            raise ValueError("Company ID and domain are required")
        
        if not isinstance(self.embedding, np.ndarray):
            raise ValueError("Embedding must be a numpy array")
        
        if self.embedding.ndim != 1:
            raise ValueError("Embedding must be a 1-dimensional array")


@dataclass
class SimilarityResult:
    """Result from similarity search."""
    
    company_id: str
    domain: str
    similarity_score: float
    metadata: Dict[str, Any]
    
    def __post_init__(self) -> None:
        """Validate similarity result after initialization."""
        if not (0.0 <= self.similarity_score <= 1.0):
            raise ValueError("Similarity score must be between 0.0 and 1.0")


class VectorStore(Protocol):
    """Protocol for vector store implementations.
    
    This protocol defines the interface for storing and querying
    company embeddings for duplicate detection.
    """
    
    @abstractmethod
    async def add_embedding(
        self,
        company_id: str,
        domain: str,
        embedding: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a company embedding to the store.
        
        Args:
            company_id: Unique company identifier.
            domain: Normalized company domain.
            embedding: Company embedding vector.
            metadata: Optional metadata dictionary.
            
        Returns:
            True if successfully added, False otherwise.
        """
        ...
    
    @abstractmethod
    async def add_embeddings_batch(
        self,
        records: List[Tuple[str, str, np.ndarray, Optional[Dict[str, Any]]]]
    ) -> int:
        """Add multiple embeddings in batch.
        
        Args:
            records: List of (company_id, domain, embedding, metadata) tuples.
            
        Returns:
            Number of successfully added embeddings.
        """
        ...
    
    @abstractmethod
    async def find_similar(
        self,
        embedding: np.ndarray,
        top_k: int = 10,
        similarity_threshold: float = 0.85,
        exclude_domains: Optional[List[str]] = None
    ) -> List[SimilarityResult]:
        """Find similar companies based on embedding.
        
        Args:
            embedding: Query embedding vector.
            top_k: Maximum number of results to return.
            similarity_threshold: Minimum similarity threshold.
            exclude_domains: Domains to exclude from results.
            
        Returns:
            List of similar companies ordered by similarity score.
        """
        ...
    
    @abstractmethod
    async def get_embedding(self, company_id: str) -> Optional[EmbeddingRecord]:
        """Get embedding record by company ID.
        
        Args:
            company_id: Company identifier.
            
        Returns:
            Embedding record if found, None otherwise.
        """
        ...
    
    @abstractmethod
    async def remove_embedding(self, company_id: str) -> bool:
        """Remove embedding by company ID.
        
        Args:
            company_id: Company identifier.
            
        Returns:
            True if successfully removed, False otherwise.
        """
        ...
    
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics.
        
        Returns:
            Dictionary with store statistics.
        """
        ...


class InMemoryVectorStore:
    """In-memory vector store implementation for testing and development.
    
    This implementation provides basic vector similarity search functionality
    using numpy operations. It is suitable for testing and small datasets
    but should be replaced with Chroma for production use.
    """
    
    def __init__(self, embedding_dimension: int = 384) -> None:
        """Initialize in-memory vector store.
        
        Args:
            embedding_dimension: Expected embedding vector dimension.
        """
        self.embedding_dimension = embedding_dimension
        self.records: Dict[str, EmbeddingRecord] = {}
        self.domain_index: Dict[str, List[str]] = {}
        self._stats = {
            'total_embeddings': 0,
            'total_queries': 0,
            'created_at': datetime.utcnow()
        }
        
        logger.info(f"Initialized InMemoryVectorStore with dimension {embedding_dimension}")
    
    async def add_embedding(
        self,
        company_id: str,
        domain: str,
        embedding: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a company embedding to the store."""
        try:
            if not company_id or not domain:
                logger.warning("Company ID and domain are required")
                return False
            
            if not isinstance(embedding, np.ndarray):
                logger.warning("Embedding must be a numpy array")
                return False
            
            if embedding.shape != (self.embedding_dimension,):
                logger.warning(
                    f"Embedding dimension mismatch: expected {self.embedding_dimension}, "
                    f"got {embedding.shape}"
                )
                return False
            
            # Normalize embedding for cosine similarity
            normalized_embedding = embedding / np.linalg.norm(embedding)
            
            # Create record
            record = EmbeddingRecord(
                company_id=company_id,
                domain=domain.lower(),
                embedding=normalized_embedding,
                metadata=metadata or {},
                created_at=datetime.utcnow()
            )
            
            # Store record
            self.records[company_id] = record
            
            # Update domain index
            if domain not in self.domain_index:
                self.domain_index[domain] = []
            if company_id not in self.domain_index[domain]:
                self.domain_index[domain].append(company_id)
            
            # Update stats
            self._stats['total_embeddings'] = len(self.records)
            
            logger.debug(f"Added embedding for company {company_id} with domain {domain}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add embedding for company {company_id}: {e}")
            return False
    
    async def add_embeddings_batch(
        self,
        records: List[Tuple[str, str, np.ndarray, Optional[Dict[str, Any]]]]
    ) -> int:
        """Add multiple embeddings in batch."""
        successful_count = 0
        
        for company_id, domain, embedding, metadata in records:
            if await self.add_embedding(company_id, domain, embedding, metadata):
                successful_count += 1
        
        logger.info(f"Added {successful_count}/{len(records)} embeddings in batch")
        return successful_count
    
    async def find_similar(
        self,
        embedding: np.ndarray,
        top_k: int = 10,
        similarity_threshold: float = 0.85,
        exclude_domains: Optional[List[str]] = None
    ) -> List[SimilarityResult]:
        """Find similar companies based on embedding."""
        try:
            if not isinstance(embedding, np.ndarray):
                logger.warning("Query embedding must be a numpy array")
                return []
            
            if embedding.shape != (self.embedding_dimension,):
                logger.warning(
                    f"Query embedding dimension mismatch: expected {self.embedding_dimension}, "
                    f"got {embedding.shape}"
                )
                return []
            
            # Normalize query embedding
            normalized_query = embedding / np.linalg.norm(embedding)
            
            # Prepare exclusion set
            exclude_set = set(exclude_domains or [])
            
            # Calculate similarities
            similarities = []
            for record in self.records.values():
                # Skip excluded domains
                if record.domain in exclude_set:
                    continue
                
                # Calculate cosine similarity
                similarity = np.dot(normalized_query, record.embedding)
                
                # Apply threshold
                if similarity >= similarity_threshold:
                    similarities.append(SimilarityResult(
                        company_id=record.company_id,
                        domain=record.domain,
                        similarity_score=float(similarity),
                        metadata=record.metadata.copy()
                    ))
            
            # Sort by similarity and limit results
            similarities.sort(key=lambda x: x.similarity_score, reverse=True)
            results = similarities[:top_k]
            
            # Update stats
            self._stats['total_queries'] += 1
            
            logger.debug(
                f"Found {len(results)} similar companies above threshold {similarity_threshold}"
            )
            return results
            
        except Exception as e:
            logger.error(f"Failed to find similar companies: {e}")
            return []
    
    async def get_embedding(self, company_id: str) -> Optional[EmbeddingRecord]:
        """Get embedding record by company ID."""
        return self.records.get(company_id)
    
    async def remove_embedding(self, company_id: str) -> bool:
        """Remove embedding by company ID."""
        try:
            if company_id not in self.records:
                return False
            
            record = self.records[company_id]
            domain = record.domain
            
            # Remove from records
            del self.records[company_id]
            
            # Update domain index
            if domain in self.domain_index:
                if company_id in self.domain_index[domain]:
                    self.domain_index[domain].remove(company_id)
                if not self.domain_index[domain]:
                    del self.domain_index[domain]
            
            # Update stats
            self._stats['total_embeddings'] = len(self.records)
            
            logger.debug(f"Removed embedding for company {company_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove embedding for company {company_id}: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics."""
        return {
            **self._stats,
            'unique_domains': len(self.domain_index),
            'embedding_dimension': self.embedding_dimension,
            'memory_usage_mb': self._estimate_memory_usage()
        }
    
    def _estimate_memory_usage(self) -> float:
        """Estimate memory usage in MB."""
        try:
            # Rough estimation based on number of embeddings and dimension
            embedding_size_bytes = len(self.records) * self.embedding_dimension * 8  # float64
            metadata_size_bytes = len(self.records) * 1024  # Rough estimate for metadata
            total_bytes = embedding_size_bytes + metadata_size_bytes
            return total_bytes / (1024 * 1024)  # Convert to MB
        except Exception:
            return 0.0


class ChromaVectorStore:
    """Production Chroma vector store implementation for semantic search.
    
    This implementation provides full integration with ChromaDB for scalable
    vector similarity search, embedding generation, and duplicate detection.
    """
    
    def __init__(
        self,
        persist_directory: str = "./data/chroma_db",
        collection_name: str = "company_embeddings",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedding_dimension: int = 384,
        distance_function: str = "cosine"
    ) -> None:
        """Initialize Chroma vector store.
        
        Args:
            persist_directory: Directory for persistent storage.
            collection_name: Name of the Chroma collection.
            embedding_model: Sentence transformer model name.
            embedding_dimension: Expected embedding dimension.
            distance_function: Distance function for similarity search.
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model
        self.embedding_dimension = embedding_dimension
        self.distance_function = distance_function
        
        # Initialize components
        self._client = None
        self._collection = None
        self._embedding_model = None
        self._stats = {
            'total_embeddings': 0,
            'total_queries': 0,
            'created_at': datetime.utcnow(),
            'last_embedding_time': None,
            'last_search_time': None
        }
        
        # Initialize Chroma client and collection
        self._initialize_chroma()
        self._initialize_embedding_model()
        
        logger.info(
            f"Initialized ChromaVectorStore with collection '{collection_name}' "
            f"using model '{embedding_model}'"
        )
    
    def _initialize_chroma(self) -> None:
        """Initialize Chroma client and collection."""
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            
            # Create persist directory if it doesn't exist
            import os
            os.makedirs(self.persist_directory, exist_ok=True)
            
            # Initialize Chroma client with persistence
            self._client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Get or create collection
            try:
                self._collection = self._client.get_collection(
                    name=self.collection_name
                )
                logger.info(f"Loaded existing collection '{self.collection_name}'")
            except Exception:
                # Create new collection
                self._collection = self._client.create_collection(
                    name=self.collection_name,
                    metadata={
                        "hnsw:space": self.distance_function,
                        "embedding_model": self.embedding_model_name,
                        "embedding_dimension": self.embedding_dimension,
                        "created_at": datetime.utcnow().isoformat()
                    }
                )
                logger.info(f"Created new collection '{self.collection_name}'")
                
        except ImportError as e:
            logger.error(f"ChromaDB not installed: {e}")
            raise ImportError("ChromaDB is required. Install with: pip install chromadb")
        except Exception as e:
            logger.error(f"Failed to initialize Chroma client: {e}")
            raise
    
    def _initialize_embedding_model(self) -> None:
        """Initialize sentence transformer model."""
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"Loading embedding model: {self.embedding_model_name}")
            self._embedding_model = SentenceTransformer(self.embedding_model_name)
            
            # Verify embedding dimension
            test_embedding = self._embedding_model.encode("test")
            actual_dimension = len(test_embedding)
            
            if actual_dimension != self.embedding_dimension:
                logger.warning(
                    f"Embedding dimension mismatch: expected {self.embedding_dimension}, "
                    f"got {actual_dimension}. Updating configuration."
                )
                self.embedding_dimension = actual_dimension
                
            logger.info(f"Embedding model loaded successfully (dimension: {actual_dimension})")
            
        except ImportError as e:
            logger.error(f"sentence-transformers not installed: {e}")
            raise ImportError(
                "sentence-transformers is required. "
                "Install with: pip install sentence-transformers"
            )
        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            raise
    
    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed.
            
        Returns:
            Array of embeddings with shape (len(texts), embedding_dimension).
            
        Raises:
            ValueError: If texts list is empty or model not initialized.
        """
        if not texts:
            raise ValueError("Texts list cannot be empty")
        
        if self._embedding_model is None:
            raise ValueError("Embedding model not initialized")
        
        try:
            start_time = datetime.utcnow()
            
            # Generate embeddings
            embeddings = self._embedding_model.encode(
                texts,
                batch_size=32,
                show_progress_bar=len(texts) > 100,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            
            # Update stats
            duration = (datetime.utcnow() - start_time).total_seconds()
            self._stats['last_embedding_time'] = start_time
            
            logger.debug(
                f"Generated {len(embeddings)} embeddings in {duration:.2f}s "
                f"({duration/len(texts)*1000:.1f}ms per text)"
            )
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise
    
    def _build_company_text(self, company_data: Dict[str, Any]) -> str:
        """Build canonical text representation for embedding.
        
        Args:
            company_data: Company data dictionary.
            
        Returns:
            Canonical text string for embedding.
        """
        parts = []
        
        # Company name
        if company_data.get('company_name'):
            parts.append(f"Company: {company_data['company_name']}")
        
        # Description
        if company_data.get('description'):
            parts.append(f"Description: {company_data['description']}")
        
        # Industry
        if company_data.get('industry'):
            parts.append(f"Industry: {company_data['industry']}")
        
        # Technology signals
        if company_data.get('technology_signals'):
            tech_list = company_data['technology_signals']
            if isinstance(tech_list, list) and tech_list:
                parts.append(f"Technologies: {', '.join(tech_list[:10])}")
        
        # Product/service cues
        if company_data.get('product_service_cues'):
            product_list = company_data['product_service_cues']
            if isinstance(product_list, list) and product_list:
                parts.append(f"Products: {', '.join(product_list[:5])}")
        
        return ". ".join(parts) if parts else "Unknown company"
    
    def _generate_stable_id(self, company_data: Dict[str, Any]) -> str:
        """Generate stable document ID for company.
        
        Args:
            company_data: Company data dictionary.
            
        Returns:
            Stable document ID string.
        """
        # Use company ID if available
        if company_data.get('id'):
            return str(company_data['id'])
        
        # Use domain if available
        if company_data.get('url'):
            from urllib.parse import urlparse
            domain = urlparse(str(company_data['url'])).netloc
            return f"domain_{domain.lower()}"
        
        # Fallback to company name hash
        if company_data.get('company_name'):
            import hashlib
            name_hash = hashlib.md5(
                company_data['company_name'].lower().encode()
            ).hexdigest()[:12]
            return f"name_{name_hash}"
        
        # Last resort: generate UUID
        import uuid
        return f"uuid_{str(uuid.uuid4())[:8]}"
    
    async def add_embedding(
        self,
        company_id: str,
        domain: str,
        embedding: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a company embedding to Chroma.
        
        Args:
            company_id: Unique company identifier.
            domain: Normalized company domain.
            embedding: Company embedding vector.
            metadata: Optional metadata dictionary.
            
        Returns:
            True if successfully added, False otherwise.
        """
        try:
            if not company_id or not domain:
                logger.warning("Company ID and domain are required")
                return False
            
            if not isinstance(embedding, np.ndarray):
                logger.warning("Embedding must be a numpy array")
                return False
            
            if embedding.shape != (self.embedding_dimension,):
                logger.warning(
                    f"Embedding dimension mismatch: expected {self.embedding_dimension}, "
                    f"got {embedding.shape}"
                )
                return False
            
            # Prepare metadata
            full_metadata = {
                'domain': domain.lower(),
                'added_at': datetime.utcnow().isoformat(),
                **(metadata or {})
            }
            
            # Add to Chroma collection
            self._collection.upsert(
                ids=[company_id],
                embeddings=[embedding.tolist()],
                metadatas=[full_metadata]
            )
            
            # Update stats
            self._stats['total_embeddings'] = self._collection.count()
            
            logger.debug(f"Added embedding for company {company_id} with domain {domain}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add embedding for company {company_id}: {e}")
            return False
    
    async def add_embeddings_batch(
        self,
        records: List[Tuple[str, str, np.ndarray, Optional[Dict[str, Any]]]]
    ) -> int:
        """Add multiple embeddings to Chroma in batch.
        
        Args:
            records: List of (company_id, domain, embedding, metadata) tuples.
            
        Returns:
            Number of successfully added embeddings.
        """
        if not records:
            return 0
        
        try:
            # Prepare batch data
            ids = []
            embeddings = []
            metadatas = []
            
            for company_id, domain, embedding, metadata in records:
                # Validate record
                if not company_id or not domain:
                    logger.warning(f"Skipping invalid record: {company_id}, {domain}")
                    continue
                
                if not isinstance(embedding, np.ndarray):
                    logger.warning(f"Skipping non-array embedding for {company_id}")
                    continue
                
                if embedding.shape != (self.embedding_dimension,):
                    logger.warning(f"Skipping wrong dimension embedding for {company_id}")
                    continue
                
                # Prepare metadata
                full_metadata = {
                    'domain': domain.lower(),
                    'added_at': datetime.utcnow().isoformat(),
                    **(metadata or {})
                }
                
                ids.append(company_id)
                embeddings.append(embedding.tolist())
                metadatas.append(full_metadata)
            
            if not ids:
                logger.warning("No valid records to add")
                return 0
            
            # Batch upsert to Chroma
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas
            )
            
            # Update stats
            self._stats['total_embeddings'] = self._collection.count()
            
            logger.info(f"Added {len(ids)} embeddings in batch")
            return len(ids)
            
        except Exception as e:
            logger.error(f"Failed to add embeddings batch: {e}")
            return 0
    
    async def find_similar(
        self,
        embedding: np.ndarray,
        top_k: int = 10,
        similarity_threshold: float = 0.85,
        exclude_domains: Optional[List[str]] = None
    ) -> List[SimilarityResult]:
        """Find similar companies based on embedding.
        
        Args:
            embedding: Query embedding vector.
            top_k: Maximum number of results to return.
            similarity_threshold: Minimum similarity threshold.
            exclude_domains: Domains to exclude from results.
            
        Returns:
            List of similar companies ordered by similarity score.
        """
        try:
            start_time = datetime.utcnow()
            
            if not isinstance(embedding, np.ndarray):
                logger.warning("Query embedding must be a numpy array")
                return []
            
            if embedding.shape != (self.embedding_dimension,):
                logger.warning(
                    f"Query embedding dimension mismatch: expected {self.embedding_dimension}, "
                    f"got {embedding.shape}"
                )
                return []
            
            # Query Chroma collection
            results = self._collection.query(
                query_embeddings=[embedding.tolist()],
                n_results=min(top_k * 2, 100),  # Get more results to filter
                include=['metadatas', 'distances']
            )
            
            # Process results
            similarities = []
            exclude_set = set((exclude_domains or []))
            
            if results['ids'] and results['ids'][0]:
                for i, company_id in enumerate(results['ids'][0]):
                    distance = results['distances'][0][i]
                    metadata = results['metadatas'][0][i]
                    
                    # Convert distance to similarity (for cosine distance)
                    similarity = 1.0 - distance
                    
                    # Apply threshold
                    if similarity < similarity_threshold:
                        continue
                    
                    # Check exclusions
                    domain = metadata.get('domain', '')
                    if domain in exclude_set:
                        continue
                    
                    similarities.append(SimilarityResult(
                        company_id=company_id,
                        domain=domain,
                        similarity_score=float(similarity),
                        metadata=metadata
                    ))
            
            # Sort by similarity and limit results
            similarities.sort(key=lambda x: x.similarity_score, reverse=True)
            final_results = similarities[:top_k]
            
            # Update stats
            duration = (datetime.utcnow() - start_time).total_seconds()
            self._stats['total_queries'] += 1
            self._stats['last_search_time'] = start_time
            
            logger.debug(
                f"Found {len(final_results)} similar companies above threshold "
                f"{similarity_threshold} in {duration*1000:.1f}ms"
            )
            
            return final_results
            
        except Exception as e:
            logger.error(f"Failed to find similar companies: {e}")
            return []
    
    async def get_embedding(self, company_id: str) -> Optional[EmbeddingRecord]:
        """Get embedding record by company ID.
        
        Args:
            company_id: Company identifier.
            
        Returns:
            Embedding record if found, None otherwise.
        """
        try:
            results = self._collection.get(
                ids=[company_id],
                include=['embeddings', 'metadatas']
            )
            
            if results['ids'] and results['ids'][0] == company_id:
                embedding_list = results['embeddings'][0]
                metadata = results['metadatas'][0]
                
                return EmbeddingRecord(
                    company_id=company_id,
                    domain=metadata.get('domain', ''),
                    embedding=np.array(embedding_list),
                    metadata=metadata,
                    created_at=datetime.fromisoformat(
                        metadata.get('added_at', datetime.utcnow().isoformat())
                    )
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get embedding for company {company_id}: {e}")
            return None
    
    async def remove_embedding(self, company_id: str) -> bool:
        """Remove embedding by company ID.
        
        Args:
            company_id: Company identifier.
            
        Returns:
            True if successfully removed, False otherwise.
        """
        try:
            # Check if exists first
            existing = await self.get_embedding(company_id)
            if not existing:
                return False
            
            # Delete from collection
            self._collection.delete(ids=[company_id])
            
            # Update stats
            self._stats['total_embeddings'] = self._collection.count()
            
            logger.debug(f"Removed embedding for company {company_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove embedding for company {company_id}: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get Chroma collection statistics.
        
        Returns:
            Dictionary with store statistics.
        """
        try:
            # Get collection count
            count = self._collection.count()
            
            # Estimate storage size
            storage_size_mb = self._estimate_storage_size()
            
            return {
                **self._stats,
                'total_embeddings': count,
                'collection_name': self.collection_name,
                'embedding_dimension': self.embedding_dimension,
                'embedding_model': self.embedding_model_name,
                'distance_function': self.distance_function,
                'storage_size_mb': storage_size_mb,
                'persist_directory': self.persist_directory
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection statistics: {e}")
            return {
                **self._stats,
                'error': str(e)
            }
    
    def _estimate_storage_size(self) -> float:
        """Estimate storage size in MB."""
        try:
            import os
            
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(self.persist_directory):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
            
            return total_size / (1024 * 1024)  # Convert to MB
            
        except Exception:
            return 0.0
    
    async def add_company_embeddings(self, companies: List[Dict[str, Any]]) -> bool:
        """Add embeddings for multiple companies.
        
        Args:
            companies: List of company data dictionaries.
            
        Returns:
            True if all companies processed successfully, False otherwise.
        """
        if not companies:
            return True
        
        try:
            # Build texts for embedding
            texts = []
            company_ids = []
            domains = []
            metadatas = []
            
            for company_data in companies:
                # Generate stable ID
                company_id = self._generate_stable_id(company_data)
                
                # Build embedding text
                text = self._build_company_text(company_data)
                
                # Extract domain
                domain = "unknown"
                if company_data.get('url'):
                    from urllib.parse import urlparse
                    domain = urlparse(str(company_data['url'])).netloc.lower()
                
                # Prepare metadata
                metadata = {
                    'country': company_data.get('country', ''),
                    'industry': company_data.get('industry', ''),
                    'source': company_data.get('source', ''),
                    'score': company_data.get('score', 0)
                }
                
                texts.append(text)
                company_ids.append(company_id)
                domains.append(domain)
                metadatas.append(metadata)
            
            # Generate embeddings
            embeddings = self.generate_embeddings(texts)
            
            # Prepare batch records
            records = []
            for i in range(len(company_ids)):
                records.append((
                    company_ids[i],
                    domains[i],
                    embeddings[i],
                    metadatas[i]
                ))
            
            # Add to vector store
            successful_count = await self.add_embeddings_batch(records)
            
            success = successful_count == len(companies)
            logger.info(
                f"Added embeddings for {successful_count}/{len(companies)} companies"
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to add company embeddings: {e}")
            return False
    
    async def search_similar_companies(
        self,
        query: str,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        **filters
    ) -> List[Dict[str, Any]]:
        """Search for similar companies using text query.
        
        Args:
            query: Text query for semantic search.
            limit: Maximum number of results.
            similarity_threshold: Minimum similarity threshold.
            **filters: Additional metadata filters.
            
        Returns:
            List of similar company results.
        """
        try:
            # Generate query embedding
            query_embeddings = self.generate_embeddings([query])
            query_embedding = query_embeddings[0]
            
            # Find similar companies
            results = await self.find_similar(
                embedding=query_embedding,
                top_k=limit,
                similarity_threshold=similarity_threshold,
                exclude_domains=filters.get('exclude_domains')
            )
            
            # Convert to dictionary format
            similar_companies = []
            for result in results:
                similar_companies.append({
                    'company_id': result.company_id,
                    'domain': result.domain,
                    'similarity_score': result.similarity_score,
                    'metadata': result.metadata
                })
            
            return similar_companies
            
        except Exception as e:
            logger.error(f"Failed to search similar companies: {e}")
            return []
    
    async def find_duplicates(
        self,
        company_data: Dict[str, Any],
        threshold: float = 0.85
    ) -> List[str]:
        """Find potential duplicate companies.
        
        Args:
            company_data: Company data to check for duplicates.
            threshold: Similarity threshold for duplicates.
            
        Returns:
            List of company IDs that are potential duplicates.
        """
        try:
            # Build embedding text
            text = self._build_company_text(company_data)
            
            # Generate embedding
            embeddings = self.generate_embeddings([text])
            embedding = embeddings[0]
            
            # Find similar companies
            results = await self.find_similar(
                embedding=embedding,
                top_k=50,
                similarity_threshold=threshold
            )
            
            # Extract company IDs
            duplicate_ids = [result.company_id for result in results]
            
            logger.debug(f"Found {len(duplicate_ids)} potential duplicates")
            return duplicate_ids
            
        except Exception as e:
            logger.error(f"Failed to find duplicates: {e}")
            return []
    
    async def initialize_collection(self, collection_name: str) -> bool:
        """Initialize or switch to a different collection.
        
        Args:
            collection_name: Name of the collection to initialize.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            old_collection_name = self.collection_name
            self.collection_name = collection_name
            
            # Try to get existing collection
            try:
                self._collection = self._client.get_collection(name=collection_name)
                logger.info(f"Switched to existing collection '{collection_name}'")
            except Exception:
                # Create new collection
                self._collection = self._client.create_collection(
                    name=collection_name,
                    metadata={
                        "hnsw:space": self.distance_function,
                        "embedding_model": self.embedding_model_name,
                        "embedding_dimension": self.embedding_dimension,
                        "created_at": datetime.utcnow().isoformat()
                    }
                )
                logger.info(f"Created new collection '{collection_name}'")
            
            # Update stats
            self._stats['total_embeddings'] = self._collection.count()
            
            return True
            
        except Exception as e:
            # Revert to old collection name on failure
            self.collection_name = old_collection_name
            logger.error(f"Failed to initialize collection '{collection_name}': {e}")
            return False