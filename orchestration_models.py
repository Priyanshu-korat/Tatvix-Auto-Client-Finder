"""Orchestration models for the Tatvix AI Client Discovery System.

This module defines Pydantic models for pipeline execution results,
health monitoring, error recovery, and performance reporting.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field, validator
import uuid


class PipelineStage(str, Enum):
    """Pipeline execution stage enumeration."""
    INITIALIZATION = "initialization"
    HEALTH_CHECK = "health_check"
    SEARCH_DISCOVERY = "search_discovery"
    MULTI_SOURCE_DISCOVERY = "multi_source_discovery"
    WEBSITE_SCRAPING = "website_scraping"
    EMAIL_DISCOVERY = "email_discovery"
    AI_ANALYSIS = "ai_analysis"
    DUPLICATE_DETECTION = "duplicate_detection"
    DATA_STORAGE = "data_storage"
    VECTOR_INDEXING = "vector_indexing"
    VALIDATION = "validation"
    REPORTING = "reporting"


class ExecutionStatus(str, Enum):
    """Execution status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    DEGRADED = "degraded"


class HealthLevel(str, Enum):
    """System health level enumeration."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class RecoveryActionType(str, Enum):
    """Recovery action type enumeration."""
    RETRY = "retry"
    SKIP = "skip"
    ABORT_STAGE = "abort_stage"
    ABORT_RUN = "abort_run"
    CONTINUE = "continue"
    FALLBACK = "fallback"


class StageResult(BaseModel):
    """Individual pipeline stage execution result."""
    
    stage: PipelineStage = Field(..., description="Pipeline stage identifier")
    status: ExecutionStatus = Field(..., description="Stage execution status")
    started_at: datetime = Field(..., description="Stage start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Stage completion timestamp")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Stage execution duration")
    
    # Results and metrics
    items_processed: int = Field(default=0, ge=0, description="Number of items processed")
    items_successful: int = Field(default=0, ge=0, description="Number of successful items")
    items_failed: int = Field(default=0, ge=0, description="Number of failed items")
    
    # Error information
    error_message: Optional[str] = Field(None, description="Error message if stage failed")
    error_details: Dict[str, Any] = Field(default_factory=dict, description="Detailed error information")
    
    # Stage-specific metrics
    stage_metrics: Dict[str, Any] = Field(default_factory=dict, description="Stage-specific performance metrics")
    
    @validator('duration_seconds', pre=True, always=True)
    def calculate_duration(cls, v: float, values: Dict[str, Any]) -> float:
        """Calculate duration from timestamps if not provided."""
        if v > 0:
            return v
        
        started_at = values.get('started_at')
        completed_at = values.get('completed_at')
        
        if started_at and completed_at:
            return (completed_at - started_at).total_seconds()
        
        return 0.0
    
    @validator('items_successful')
    def validate_successful_items(cls, v: int, values: Dict[str, Any]) -> int:
        """Validate successful items don't exceed processed items."""
        items_processed = values.get('items_processed', 0)
        return min(v, items_processed)
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class PipelineResult(BaseModel):
    """Complete pipeline execution result."""
    
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique execution identifier")
    pipeline_version: str = Field(default="1.0", description="Pipeline version")
    
    # Execution metadata
    started_at: datetime = Field(default_factory=datetime.utcnow, description="Pipeline start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Pipeline completion timestamp")
    total_duration_seconds: float = Field(default=0.0, ge=0.0, description="Total pipeline duration")
    
    # Overall status
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING, description="Overall pipeline status")
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Pipeline success rate")
    
    # Stage results
    stage_results: List[StageResult] = Field(default_factory=list, description="Individual stage results")
    failed_stages: List[PipelineStage] = Field(default_factory=list, description="Stages that failed")
    
    # Lead processing results
    total_leads_discovered: int = Field(default=0, ge=0, description="Total leads discovered")
    leads_processed: int = Field(default=0, ge=0, description="Leads successfully processed")
    leads_stored: int = Field(default=0, ge=0, description="Leads stored in database")
    duplicates_filtered: int = Field(default=0, ge=0, description="Duplicate leads filtered")
    
    # Quality metrics
    average_lead_score: Optional[float] = Field(None, ge=0.0, le=10.0, description="Average lead quality score")
    high_quality_leads: int = Field(default=0, ge=0, description="High quality leads (score >= 7)")
    
    # Error summary
    total_errors: int = Field(default=0, ge=0, description="Total errors encountered")
    error_summary: Dict[str, int] = Field(default_factory=dict, description="Error counts by type")
    
    @validator('total_duration_seconds', pre=True, always=True)
    def calculate_total_duration(cls, v: float, values: Dict[str, Any]) -> float:
        """Calculate total duration from timestamps if not provided."""
        if v > 0:
            return v
        
        started_at = values.get('started_at')
        completed_at = values.get('completed_at')
        
        if started_at and completed_at:
            return (completed_at - started_at).total_seconds()
        
        return 0.0
    
    @validator('success_rate', pre=True, always=True)
    def calculate_success_rate(cls, v: float, values: Dict[str, Any]) -> float:
        """Calculate success rate from stage results if not provided."""
        if v > 0:
            return v
        
        stage_results = values.get('stage_results', [])
        if not stage_results:
            return 0.0
        
        successful_stages = sum(1 for stage in stage_results if stage.status == ExecutionStatus.COMPLETED)
        return successful_stages / len(stage_results)
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
        validate_assignment = True


class ComponentHealth(BaseModel):
    """Individual component health status."""
    
    component_name: str = Field(..., min_length=1, description="Component name")
    health_level: HealthLevel = Field(..., description="Component health level")
    status_message: str = Field(..., description="Human-readable status message")
    
    # Health metrics
    last_check_at: datetime = Field(default_factory=datetime.utcnow, description="Last health check timestamp")
    response_time_ms: Optional[float] = Field(None, ge=0.0, description="Component response time")
    
    # Component-specific details
    details: Dict[str, Any] = Field(default_factory=dict, description="Component-specific health details")
    recommendations: List[str] = Field(default_factory=list, description="Health improvement recommendations")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class HealthStatus(BaseModel):
    """System-wide health status."""
    
    overall_health: HealthLevel = Field(..., description="Overall system health level")
    check_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Health check timestamp")
    
    # Component health
    component_health: List[ComponentHealth] = Field(default_factory=list, description="Individual component health")
    healthy_components: int = Field(default=0, ge=0, description="Number of healthy components")
    warning_components: int = Field(default=0, ge=0, description="Number of components with warnings")
    critical_components: int = Field(default=0, ge=0, description="Number of critical components")
    
    # System resources
    system_resources: Dict[str, Any] = Field(default_factory=dict, description="System resource utilization")
    
    # Configuration validation
    configuration_valid: bool = Field(default=True, description="Whether system configuration is valid")
    missing_credentials: List[str] = Field(default_factory=list, description="Missing required credentials")
    
    @validator('overall_health', pre=True, always=True)
    def calculate_overall_health(cls, v: HealthLevel, values: Dict[str, Any]) -> HealthLevel:
        """Calculate overall health from component health if not provided."""
        component_health = values.get('component_health', [])
        if not component_health:
            return v
        
        # If any component is critical, overall health is critical
        if any(comp.health_level == HealthLevel.CRITICAL for comp in component_health):
            return HealthLevel.CRITICAL
        
        # If any component has warnings, overall health is warning
        if any(comp.health_level == HealthLevel.WARNING for comp in component_health):
            return HealthLevel.WARNING
        
        # If all components are healthy, overall health is healthy
        if all(comp.health_level == HealthLevel.HEALTHY for comp in component_health):
            return HealthLevel.HEALTHY
        
        return HealthLevel.UNKNOWN
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class RecoveryAction(BaseModel):
    """Error recovery action specification."""
    
    action_type: RecoveryActionType = Field(..., description="Type of recovery action")
    stage: PipelineStage = Field(..., description="Stage where error occurred")
    error_type: str = Field(..., description="Type of error encountered")
    
    # Action parameters
    retry_count: int = Field(default=0, ge=0, description="Number of retries attempted")
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")
    retry_delay_seconds: float = Field(default=1.0, ge=0.0, description="Delay between retries")
    
    # Recovery details
    recovery_reason: str = Field(..., description="Reason for recovery action")
    fallback_options: List[str] = Field(default_factory=list, description="Available fallback options")
    
    # Execution metadata
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Recovery action creation time")
    executed_at: Optional[datetime] = Field(None, description="Recovery action execution time")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
        validate_assignment = True


class PerformanceMetrics(BaseModel):
    """Performance metrics for a specific aspect of the pipeline."""
    
    metric_name: str = Field(..., min_length=1, description="Metric name")
    metric_value: Union[int, float, str] = Field(..., description="Metric value")
    metric_unit: str = Field(..., description="Metric unit (e.g., 'seconds', 'count', 'percentage')")
    
    # Metric metadata
    measurement_time: datetime = Field(default_factory=datetime.utcnow, description="Measurement timestamp")
    target_value: Optional[Union[int, float]] = Field(None, description="Target value for this metric")
    threshold_warning: Optional[Union[int, float]] = Field(None, description="Warning threshold")
    threshold_critical: Optional[Union[int, float]] = Field(None, description="Critical threshold")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class PerformanceReport(BaseModel):
    """Comprehensive performance report for pipeline execution."""
    
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique report identifier")
    execution_id: str = Field(..., description="Associated pipeline execution ID")
    
    # Report metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Report generation timestamp")
    report_period_start: datetime = Field(..., description="Report period start time")
    report_period_end: datetime = Field(..., description="Report period end time")
    
    # Overall performance summary
    total_execution_time: float = Field(..., ge=0.0, description="Total execution time in seconds")
    throughput_leads_per_hour: float = Field(default=0.0, ge=0.0, description="Lead processing throughput")
    success_rate_percentage: float = Field(..., ge=0.0, le=100.0, description="Overall success rate")
    
    # Stage performance
    stage_performance: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Performance metrics by pipeline stage"
    )
    
    # Resource utilization
    resource_utilization: Dict[str, PerformanceMetrics] = Field(
        default_factory=dict,
        description="System resource utilization metrics"
    )
    
    # Quality metrics
    quality_metrics: Dict[str, PerformanceMetrics] = Field(
        default_factory=dict,
        description="Data quality and accuracy metrics"
    )
    
    # Error analysis
    error_analysis: Dict[str, Any] = Field(default_factory=dict, description="Error pattern analysis")
    
    # Performance trends
    performance_trends: Dict[str, List[float]] = Field(
        default_factory=dict,
        description="Performance trends over time"
    )
    
    # Recommendations
    performance_recommendations: List[str] = Field(
        default_factory=list,
        description="Performance improvement recommendations"
    )
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class ExecutionResult(BaseModel):
    """Top-level execution result containing all pipeline information."""
    
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique execution identifier")
    
    # Execution configuration
    configuration_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Configuration used for execution")
    feature_flags: Dict[str, bool] = Field(default_factory=dict, description="Feature flags active during execution")
    
    # Results
    pipeline_result: PipelineResult = Field(..., description="Pipeline execution result")
    health_status: HealthStatus = Field(..., description="System health at execution time")
    performance_report: PerformanceReport = Field(..., description="Performance analysis report")
    
    # Recovery actions taken
    recovery_actions: List[RecoveryAction] = Field(default_factory=list, description="Recovery actions executed")
    
    # Output artifacts
    output_files: List[str] = Field(default_factory=list, description="Generated output file paths")
    log_files: List[str] = Field(default_factory=list, description="Associated log file paths")
    
    # Execution summary
    execution_summary: str = Field(..., description="Human-readable execution summary")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
        validate_assignment = True


class PipelineConfiguration(BaseModel):
    """Pipeline execution configuration."""
    
    # Feature flags
    enable_search_discovery: bool = Field(default=True, description="Enable web search discovery")
    enable_multi_source_discovery: bool = Field(default=True, description="Enable multi-source discovery")
    enable_website_scraping: bool = Field(default=True, description="Enable website scraping")
    enable_email_discovery: bool = Field(default=True, description="Enable email discovery")
    enable_ai_analysis: bool = Field(default=True, description="Enable AI analysis")
    enable_duplicate_detection: bool = Field(default=True, description="Enable duplicate detection")
    enable_vector_indexing: bool = Field(default=True, description="Enable vector indexing")
    
    # Processing limits
    max_leads_per_source: int = Field(default=100, ge=1, le=1000, description="Maximum leads per source")
    max_concurrent_operations: int = Field(default=5, ge=1, le=20, description="Maximum concurrent operations")
    pipeline_timeout_minutes: int = Field(default=240, ge=30, le=720, description="Pipeline timeout in minutes")
    
    # Quality thresholds
    min_lead_score: int = Field(default=3, ge=1, le=10, description="Minimum lead quality score")
    duplicate_similarity_threshold: float = Field(default=0.9, ge=0.5, le=1.0, description="Duplicate similarity threshold")
    
    # Error handling
    max_stage_retries: int = Field(default=3, ge=0, le=10, description="Maximum retries per stage")
    continue_on_stage_failure: bool = Field(default=True, description="Continue pipeline on non-critical stage failure")
    
    # Output configuration
    generate_performance_report: bool = Field(default=True, description="Generate performance report")
    save_intermediate_results: bool = Field(default=False, description="Save intermediate stage results")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True