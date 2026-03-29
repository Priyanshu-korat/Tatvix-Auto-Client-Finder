"""Vector database models for Prompt 9 implementation.

This module defines Pydantic models specifically for vector database operations,
embedding generation, and semantic search functionality.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator


class SimilarCompanyResult(BaseModel):
    """Result from vector similarity search."""
    
    company_id: str = Field(..., min_length=1, description="Unique company identifier")
    domain: str = Field(..., min_length=1, description="Company domain")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Cosine similarity score")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Company metadata")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class EmbeddingGenerationRequest(BaseModel):
    """Request for generating company embeddings."""
    
    companies: List[Dict[str, Any]] = Field(..., min_items=1, description="Company data for embedding")
    batch_size: int = Field(default=32, ge=1, le=128, description="Batch size for processing")
    force_regenerate: bool = Field(default=False, description="Force regeneration of existing embeddings")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class EmbeddingGenerationResult(BaseModel):
    """Result from embedding generation."""
    
    success: bool = Field(..., description="Generation success status")
    total_companies: int = Field(..., ge=0, description="Total companies processed")
    successful_embeddings: int = Field(..., ge=0, description="Successfully generated embeddings")
    failed_embeddings: int = Field(..., ge=0, description="Failed embedding generations")
    processing_time_seconds: float = Field(..., ge=0.0, description="Total processing time")
    average_time_per_company: float = Field(..., ge=0.0, description="Average time per company")
    
    # Error details
    errors: List[Dict[str, str]] = Field(default_factory=list, description="Error details for failed embeddings")
    
    @validator('successful_embeddings')
    def validate_successful_count(cls, v: int, values: Dict[str, Any]) -> int:
        """Validate successful embeddings count."""
        total = values.get('total_companies', 0)
        failed = values.get('failed_embeddings', 0)
        expected = total - failed
        if v != expected:
            return expected
        return v
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class VectorSearchRequest(BaseModel):
    """Request for vector similarity search."""
    
    query_text: Optional[str] = Field(None, description="Text query for semantic search")
    query_embedding: Optional[List[float]] = Field(None, description="Pre-computed query embedding")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of results")
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Minimum similarity threshold")
    
    # Metadata filters
    country_filter: Optional[str] = Field(None, description="Filter by country")
    industry_filter: Optional[str] = Field(None, description="Filter by industry")
    source_filter: Optional[str] = Field(None, description="Filter by source")
    
    # Exclusions
    exclude_domains: List[str] = Field(default_factory=list, description="Domains to exclude from results")
    exclude_company_ids: List[str] = Field(default_factory=list, description="Company IDs to exclude")
    
    @validator('query_text', 'query_embedding')
    def validate_query_input(cls, v: Any, values: Dict[str, Any], field: Any) -> Any:
        """Ensure either query_text or query_embedding is provided."""
        if field.name == 'query_embedding' and v is None:
            query_text = values.get('query_text')
            if not query_text:
                raise ValueError("Either query_text or query_embedding must be provided")
        return v
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class VectorSearchResult(BaseModel):
    """Result from vector similarity search."""
    
    success: bool = Field(..., description="Search success status")
    query_text: Optional[str] = Field(None, description="Original query text")
    results: List[SimilarCompanyResult] = Field(default_factory=list, description="Search results")
    total_results: int = Field(..., ge=0, description="Total number of results found")
    search_time_ms: float = Field(..., ge=0.0, description="Search execution time in milliseconds")
    
    # Search metadata
    similarity_threshold_used: float = Field(..., ge=0.0, le=1.0, description="Similarity threshold applied")
    filters_applied: Dict[str, Any] = Field(default_factory=dict, description="Filters that were applied")
    
    # Error information
    error_message: Optional[str] = Field(None, description="Error message if search failed")
    
    @validator('total_results')
    def validate_total_results(cls, v: int, values: Dict[str, Any]) -> int:
        """Validate total results matches results list length."""
        results = values.get('results', [])
        if isinstance(results, list):
            return len(results)
        return v
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class DuplicateSearchRequest(BaseModel):
    """Request for duplicate detection using vector similarity."""
    
    company_data: Dict[str, Any] = Field(..., description="Company data to check for duplicates")
    similarity_threshold: float = Field(default=0.85, ge=0.0, le=1.0, description="Duplicate similarity threshold")
    max_results: int = Field(default=10, ge=1, le=50, description="Maximum duplicate candidates to return")
    
    # Search scope
    check_same_domain: bool = Field(default=True, description="Include same domain matches")
    check_similar_names: bool = Field(default=True, description="Include similar company names")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class VectorStoreStats(BaseModel):
    """Vector store statistics and health metrics."""
    
    total_embeddings: int = Field(..., ge=0, description="Total number of stored embeddings")
    collection_name: str = Field(..., description="Chroma collection name")
    embedding_dimension: int = Field(..., ge=1, description="Embedding vector dimension")
    
    # Storage metrics
    storage_size_mb: float = Field(..., ge=0.0, description="Storage size in megabytes")
    memory_usage_mb: float = Field(..., ge=0.0, description="Memory usage in megabytes")
    
    # Performance metrics
    last_indexing_time: Optional[datetime] = Field(None, description="Last indexing operation timestamp")
    average_search_time_ms: float = Field(..., ge=0.0, description="Average search time in milliseconds")
    
    # Health indicators
    is_healthy: bool = Field(..., description="Overall health status")
    last_health_check: datetime = Field(default_factory=datetime.utcnow, description="Last health check timestamp")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class VectorBackupResult(BaseModel):
    """Result from vector database backup operation."""
    
    success: bool = Field(..., description="Backup success status")
    backup_path: str = Field(..., description="Path to backup directory")
    collection_name: str = Field(..., description="Backed up collection name")
    
    # Backup metrics
    embeddings_backed_up: int = Field(..., ge=0, description="Number of embeddings backed up")
    backup_size_mb: float = Field(..., ge=0.0, description="Backup size in megabytes")
    backup_duration_seconds: float = Field(..., ge=0.0, description="Backup duration")
    
    # Backup metadata
    backup_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Backup creation time")
    backup_format: str = Field(default="chroma_native", description="Backup format used")
    
    # Error information
    error_message: Optional[str] = Field(None, description="Error message if backup failed")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True