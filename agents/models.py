"""Data models for search agents and results.

This module defines Pydantic models for structured data handling
in the search and discovery pipeline.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, HttpUrl, Field, validator


class SearchStatus(str, Enum):
    """Search execution status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TargetType(str, Enum):
    """Target company type enumeration."""
    IOT_SOFTWARE = "iot_software"
    EMBEDDED_SYSTEMS = "embedded_systems"
    HARDWARE_STARTUP = "hardware_startup"
    INDUSTRY_SPECIFIC = "industry_specific"
    GENERAL = "general"


class BusinessType(str, Enum):
    """Heuristic business scale classification from page content (pre-AI)."""
    UNKNOWN = "unknown"
    STARTUP = "startup"
    SME = "sme"
    ENTERPRISE = "enterprise"


class CompanySize(str, Enum):
    """Optional size bucket hints extracted from text (pre-AI)."""
    UNKNOWN = "unknown"
    STARTUP = "startup_1_10"
    SMALL = "small_11_50"
    MEDIUM = "medium_51_200"
    LARGE = "large_200_plus"


class SearchResult(BaseModel):
    """Individual search result model.
    
    Represents a single search result with validation and normalization.
    """
    
    title: str = Field(..., min_length=1, max_length=500, description="Page title")
    url: HttpUrl = Field(..., description="Normalized URL")
    snippet: Optional[str] = Field(None, max_length=1000, description="Page description snippet")
    domain: str = Field(..., min_length=1, max_length=253, description="Extracted domain")
    search_query: str = Field(..., min_length=1, description="Original search query")
    source: str = Field(default="duckduckgo", description="Search engine source")
    relevance_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Relevance score")
    discovered_at: datetime = Field(default_factory=datetime.utcnow, description="Discovery timestamp")
    
    @validator('domain', pre=True)
    def normalize_domain(cls, v: str) -> str:
        """Normalize domain to lowercase without www prefix."""
        if not v:
            raise ValueError("Domain cannot be empty")
        
        domain = v.lower().strip()
        if domain.startswith('www.'):
            domain = domain[4:]
        
        return domain
    
    @validator('title')
    def validate_title(cls, v: str) -> str:
        """Validate and clean title."""
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()
    
    @validator('snippet', pre=True)
    def clean_snippet(cls, v: Optional[str]) -> Optional[str]:
        """Clean and validate snippet."""
        if v is None:
            return None
        
        cleaned = v.strip()
        return cleaned if cleaned else None
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True


class SearchQuery(BaseModel):
    """Search query configuration model."""
    
    query: str = Field(..., min_length=1, max_length=200, description="Search query text")
    target_type: TargetType = Field(..., description="Target company type")
    country: Optional[str] = Field(None, min_length=2, max_length=2, description="ISO country code")
    region: Optional[str] = Field(None, max_length=100, description="Geographic region")
    max_results: int = Field(default=50, ge=1, le=100, description="Maximum results to return")
    timeout: int = Field(default=15, ge=5, le=60, description="Search timeout in seconds")
    
    @validator('country')
    def validate_country_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate ISO country code format."""
        if v is None:
            return None
        
        if len(v) != 2:
            raise ValueError("Country code must be 2 characters")
        
        return v.upper()
    
    @validator('query')
    def validate_query(cls, v: str) -> str:
        """Validate search query."""
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Query cannot be empty")
        
        return cleaned


class SearchBatch(BaseModel):
    """Batch search execution model."""
    
    queries: List[SearchQuery] = Field(..., min_items=1, description="List of search queries")
    batch_id: str = Field(..., min_length=1, description="Unique batch identifier")
    concurrent_limit: int = Field(default=5, ge=1, le=10, description="Concurrent search limit")
    total_timeout: int = Field(default=300, ge=60, le=1800, description="Total batch timeout")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Batch creation time")
    
    @validator('batch_id')
    def validate_batch_id(cls, v: str) -> str:
        """Validate batch ID format."""
        if not v.strip():
            raise ValueError("Batch ID cannot be empty")
        
        return v.strip()


class SearchResponse(BaseModel):
    """Complete search response model."""
    
    query: SearchQuery = Field(..., description="Original search query")
    results: List[SearchResult] = Field(default_factory=list, description="Search results")
    status: SearchStatus = Field(default=SearchStatus.PENDING, description="Search status")
    total_results: int = Field(default=0, ge=0, description="Total results found")
    execution_time: Optional[float] = Field(None, ge=0.0, description="Execution time in seconds")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    started_at: Optional[datetime] = Field(None, description="Search start time")
    completed_at: Optional[datetime] = Field(None, description="Search completion time")
    
    @validator('total_results')
    def validate_total_results(cls, v: int, values: Dict[str, Any]) -> int:
        """Validate total results matches actual results count."""
        results = values.get('results', [])
        if isinstance(results, list) and v != len(results):
            return len(results)
        return v
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
        validate_assignment = True


class SearchConfig(BaseModel):
    """Search agent configuration model."""
    
    max_results_per_query: int = Field(default=50, ge=1, le=100)
    concurrent_searches: int = Field(default=5, ge=1, le=10)
    request_timeout: int = Field(default=15, ge=5, le=60)
    retry_attempts: int = Field(default=3, ge=1, le=5)
    retry_delay: float = Field(default=1.0, ge=0.1, le=10.0)
    rate_limit_requests: int = Field(default=10, ge=1, le=100)
    rate_limit_window: int = Field(default=60, ge=10, le=300)
    cache_enabled: bool = Field(default=True)
    cache_ttl: int = Field(default=3600, ge=300, le=86400)
    user_agent: str = Field(
        default="TatvixAI-ClientFinder/1.0 (+https://tatvix.com/bot)",
        min_length=10
    )
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class CacheEntry(BaseModel):
    """Cache entry model for search results."""
    
    query_hash: str = Field(..., min_length=1, description="Query hash key")
    results: List[SearchResult] = Field(..., description="Cached search results")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Cache creation time")
    expires_at: datetime = Field(..., description="Cache expiration time")
    access_count: int = Field(default=0, ge=0, description="Number of cache hits")
    last_accessed: Optional[datetime] = Field(None, description="Last access time")
    
    @property
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return datetime.utcnow() > self.expires_at
    
    def mark_accessed(self) -> None:
        """Mark cache entry as accessed."""
        self.access_count += 1
        self.last_accessed = datetime.utcnow()
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class CompanyData(BaseModel):
    """Structured output from website scraping for downstream AI analysis."""

    url: HttpUrl = Field(..., description="Canonical scraped URL")
    success: bool = Field(default=True, description="Whether navigation and extraction completed")
    http_status: Optional[int] = Field(None, ge=100, le=599, description="HTTP status if available")
    page_title: Optional[str] = Field(None, max_length=500, description="Document or og:title")
    company_name: Optional[str] = Field(None, max_length=200, description="Resolved company or site name")
    description: Optional[str] = Field(None, max_length=2000, description="Meta or lead paragraph summary")
    industry_hints: List[str] = Field(default_factory=list, description="Industry keywords from content")
    contact_emails: List[str] = Field(default_factory=list, description="Sanitized email addresses")
    contact_phones: List[str] = Field(default_factory=list, description="Sanitized phone number strings")
    contact_hints: List[str] = Field(
        default_factory=list,
        max_length=50,
        description="Other contact-related snippets (addresses, social handles)"
    )
    technology_signals: List[str] = Field(default_factory=list, description="Detected stack indicators")
    product_service_cues: List[str] = Field(default_factory=list, description="Product or service phrases")
    business_type: BusinessType = Field(default=BusinessType.UNKNOWN, description="Heuristic business type")
    company_size_hint: CompanySize = Field(
        default=CompanySize.UNKNOWN,
        description="Heuristic company size from textual cues"
    )
    scraped_at: datetime = Field(default_factory=datetime.utcnow, description="Scrape completion time")
    error_message: Optional[str] = Field(None, max_length=1000, description="Failure detail when success is false")
    scrape_duration_seconds: Optional[float] = Field(None, ge=0.0, description="End-to-end scrape timing")

    @validator('page_title', 'company_name', 'description', 'error_message', pre=True)
    def strip_optional_text(cls, v: Optional[str]) -> Optional[str]:
        """Normalize optional string fields."""
        if v is None:
            return None
        if not isinstance(v, str):
            return None
        cleaned = v.replace('\x00', '').strip()
        return cleaned if cleaned else None

    @validator('industry_hints', 'technology_signals', 'product_service_cues', pre=True)
    def clean_string_lists(cls, v: Any) -> List[str]:
        """Drop empty entries and null bytes from string lists."""
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        out: List[str] = []
        for item in v:
            if not isinstance(item, str):
                continue
            s = item.replace('\x00', '').strip()
            if s and s not in out:
                out.append(s[:200])
        return out[:100]

    @validator('contact_emails', 'contact_phones', 'contact_hints', pre=True)
    def clean_contact_lists(cls, v: Any) -> List[str]:
        """Sanitize contact list values."""
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        out: List[str] = []
        for item in v:
            if not isinstance(item, str):
                continue
            s = item.replace('\x00', '').strip()
            if not s:
                continue
            if '<' in s or '>' in s or 'javascript:' in s.lower():
                continue
            if s not in out:
                out.append(s[:320])
        return out[:100]

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True


# AI Analysis Models for Prompt 4

class IndustryCategory(str, Enum):
    """Industry classification categories for AI analysis."""
    IOT_SOFTWARE = "iot_software"
    EMBEDDED_SYSTEMS = "embedded_systems"
    HARDWARE_MANUFACTURING = "hardware_manufacturing"
    SOFTWARE_DEVELOPMENT = "software_development"
    CONSULTING_SERVICES = "consulting_services"
    TELECOMMUNICATIONS = "telecommunications"
    AUTOMOTIVE = "automotive"
    HEALTHCARE_TECH = "healthcare_tech"
    INDUSTRIAL_AUTOMATION = "industrial_automation"
    SMART_HOME = "smart_home"
    AGRICULTURE_TECH = "agriculture_tech"
    ENERGY_UTILITIES = "energy_utilities"
    FINTECH = "fintech"
    RETAIL_ECOMMERCE = "retail_ecommerce"
    OTHER = "other"


class CompanySizeCategory(str, Enum):
    """AI-determined company size categories."""
    STARTUP = "startup_1_10"
    SMALL = "small_11_50"
    MEDIUM = "medium_51_200"
    LARGE = "large_200_plus"
    UNKNOWN = "unknown"


class BusinessStage(str, Enum):
    """Business maturity stage classification."""
    IDEA = "idea"
    MVP = "mvp"
    GROWTH = "growth"
    MATURE = "mature"
    UNKNOWN = "unknown"


class GeographicRelevance(str, Enum):
    """Geographic market relevance classification."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class TechnologyStack(str, Enum):
    """Technology stack categories."""
    EMBEDDED_C_CPP = "embedded_c_cpp"
    PYTHON_IOT = "python_iot"
    JAVASCRIPT_NODE = "javascript_node"
    JAVA_ENTERPRISE = "java_enterprise"
    DOTNET = "dotnet"
    GOLANG = "golang"
    RUST_SYSTEMS = "rust_systems"
    CLOUD_NATIVE = "cloud_native"
    MOBILE_DEVELOPMENT = "mobile_development"
    WEB_FRONTEND = "web_frontend"
    DATABASE_SYSTEMS = "database_systems"
    AI_ML = "ai_ml"
    BLOCKCHAIN = "blockchain"
    OTHER = "other"


class IndustryClassification(BaseModel):
    """AI-powered industry classification result."""
    
    primary_industry: IndustryCategory = Field(..., description="Primary industry classification")
    secondary_industries: List[IndustryCategory] = Field(
        default_factory=list,
        max_items=3,
        description="Secondary industry classifications"
    )
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Classification confidence")
    reasoning: str = Field(..., min_length=10, max_length=500, description="Classification reasoning")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class TechnologyNeeds(BaseModel):
    """AI-detected technology needs and compatibility."""
    
    detected_technologies: List[TechnologyStack] = Field(
        default_factory=list,
        max_items=10,
        description="Detected technology stack components"
    )
    iot_relevance: float = Field(..., ge=0.0, le=1.0, description="IoT technology relevance score")
    embedded_relevance: float = Field(..., ge=0.0, le=1.0, description="Embedded systems relevance score")
    cloud_integration: float = Field(..., ge=0.0, le=1.0, description="Cloud integration readiness score")
    technology_maturity: str = Field(..., min_length=5, max_length=200, description="Technology maturity assessment")
    compatibility_notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Technology compatibility observations"
    )
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class RelevanceScore(BaseModel):
    """Multi-dimensional relevance scoring for lead qualification."""
    
    iot_software_score: float = Field(..., ge=0.0, le=4.0, description="IoT software focus score (max 4)")
    embedded_systems_score: float = Field(..., ge=0.0, le=3.0, description="Embedded systems score (max 3)")
    company_size_score: float = Field(..., ge=0.0, le=3.0, description="Company size fit score (max 3)")
    technology_stack_score: float = Field(..., ge=0.0, le=2.0, description="Technology stack score (max 2)")
    geographic_score: float = Field(..., ge=0.0, le=1.0, description="Geographic match score (max 1)")
    
    total_score: float = Field(..., ge=0.0, le=13.0, description="Weighted total score")
    weighted_percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage score for comparison")
    
    score_breakdown: Dict[str, float] = Field(
        ...,
        description="Detailed score breakdown with weights applied"
    )
    
    @validator('total_score')
    def validate_total_score(cls, v: float, values: Dict[str, Any]) -> float:
        """Validate total score matches component scores."""
        component_scores = [
            values.get('iot_software_score', 0.0),
            values.get('embedded_systems_score', 0.0),
            values.get('company_size_score', 0.0),
            values.get('technology_stack_score', 0.0),
            values.get('geographic_score', 0.0)
        ]
        calculated_total = sum(component_scores)
        if abs(v - calculated_total) > 0.1:
            return calculated_total
        return v
    
    @validator('weighted_percentage')
    def validate_weighted_percentage(cls, v: float, values: Dict[str, Any]) -> float:
        """Validate weighted percentage calculation."""
        total_score = values.get('total_score', 0.0)
        calculated_percentage = (total_score / 13.0) * 100.0
        if abs(v - calculated_percentage) > 1.0:
            return calculated_percentage
        return v
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class CompanyAnalysis(BaseModel):
    """Complete AI-powered company analysis result."""
    
    company_url: HttpUrl = Field(..., description="Analyzed company URL")
    analysis_id: str = Field(..., min_length=1, description="Unique analysis identifier")
    
    # Core classifications
    industry_classification: IndustryClassification = Field(..., description="Industry analysis")
    company_size: CompanySizeCategory = Field(..., description="AI-determined company size")
    business_stage: BusinessStage = Field(..., description="Business maturity stage")
    geographic_relevance: GeographicRelevance = Field(..., description="Geographic market relevance")
    
    # Technology analysis
    technology_needs: TechnologyNeeds = Field(..., description="Technology stack and needs analysis")
    
    # Lead qualification
    relevance_score: RelevanceScore = Field(..., description="Multi-dimensional relevance scoring")
    
    # Analysis metadata
    analysis_summary: str = Field(
        ...,
        min_length=50,
        max_length=1000,
        description="Executive summary of analysis"
    )
    key_insights: List[str] = Field(
        ...,
        min_items=1,
        max_items=5,
        description="Key business insights"
    )
    recommendation: str = Field(
        ...,
        min_length=20,
        max_length=500,
        description="Lead qualification recommendation"
    )
    
    # Processing metadata
    model_used: str = Field(..., min_length=1, description="Groq model used for analysis")
    analysis_duration_seconds: float = Field(..., ge=0.0, description="Analysis processing time")
    analyzed_at: datetime = Field(default_factory=datetime.utcnow, description="Analysis timestamp")
    cache_hit: bool = Field(default=False, description="Whether result was cached")
    
    @validator('key_insights')
    def validate_key_insights(cls, v: List[str]) -> List[str]:
        """Validate key insights are meaningful."""
        validated_insights = []
        for insight in v:
            if isinstance(insight, str) and len(insight.strip()) >= 10:
                validated_insights.append(insight.strip()[:200])
        
        if not validated_insights:
            raise ValueError("At least one meaningful key insight is required")
        
        return validated_insights
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True


class AnalysisRequest(BaseModel):
    """Request model for company analysis."""
    
    company_data: CompanyData = Field(..., description="Scraped company data for analysis")
    analysis_options: Dict[str, Any] = Field(
        default_factory=dict,
        description="Analysis configuration options"
    )
    force_refresh: bool = Field(default=False, description="Force cache refresh")
    preferred_model: Optional[str] = Field(None, description="Preferred Groq model")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class AnalysisResponse(BaseModel):
    """Response model for company analysis."""
    
    success: bool = Field(..., description="Analysis success status")
    analysis: Optional[CompanyAnalysis] = Field(None, description="Analysis result if successful")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    retry_count: int = Field(default=0, ge=0, description="Number of retries performed")
    fallback_used: bool = Field(default=False, description="Whether fallback model was used")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class AnalysisCache(BaseModel):
    """Cache model for analysis results."""
    
    cache_key: str = Field(..., min_length=1, description="Stable cache key")
    analysis_result: CompanyAnalysis = Field(..., description="Cached analysis result")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Cache creation time")
    expires_at: datetime = Field(..., description="Cache expiration time")
    access_count: int = Field(default=0, ge=0, description="Cache access count")
    last_accessed: Optional[datetime] = Field(None, description="Last access timestamp")
    
    @property
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return datetime.utcnow() > self.expires_at
    
    def mark_accessed(self) -> None:
        """Mark cache entry as accessed."""
        self.access_count += 1
        self.last_accessed = datetime.utcnow()
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


# Email Discovery & Verification Models for Prompt 6

class EmailSourceType(str, Enum):
    """Email discovery source type enumeration."""
    DIRECT_EXTRACTION = "direct_extraction"
    CONTACT_PAGE = "contact_page"
    TEAM_PAGE = "team_page"
    FOOTER_EXTRACTION = "footer_extraction"
    PATTERN_GENERATION = "pattern_generation"
    MAILTO_LINK = "mailto_link"


class VerificationLevel(str, Enum):
    """Email verification level enumeration."""
    SYNTAX_ONLY = "syntax_only"
    DNS_MX = "dns_mx"
    SMTP_CONNECT = "smtp_connect"
    SMTP_RCPT = "smtp_rcpt"
    DELIVERABILITY = "deliverability"


class VerificationStatus(str, Enum):
    """Email verification status enumeration."""
    VALID = "valid"
    INVALID = "invalid"
    RISKY = "risky"
    UNKNOWN = "unknown"
    TIMEOUT = "timeout"
    ERROR = "error"


class EmailType(str, Enum):
    """Email address type classification."""
    PERSONAL = "personal"
    ROLE_BASED = "role_based"
    DISPOSABLE = "disposable"
    CATCH_ALL = "catch_all"
    UNKNOWN = "unknown"


class ComplianceFlag(str, Enum):
    """GDPR and CAN-SPAM compliance flag enumeration."""
    PRIVACY_POLICY_PRESENT = "privacy_policy_present"
    CONTACT_INFO_PUBLIC = "contact_info_public"
    UNSUBSCRIBE_MECHANISM = "unsubscribe_mechanism"
    DATA_PROCESSING_NOTICE = "data_processing_notice"
    COOKIE_CONSENT = "cookie_consent"
    TERMS_OF_SERVICE = "terms_of_service"


class EmailCandidate(BaseModel):
    """Individual email candidate from discovery process."""
    
    email_address: str = Field(..., min_length=5, max_length=254, description="Email address")
    source_type: EmailSourceType = Field(..., description="Discovery source type")
    source_page_url: Optional[HttpUrl] = Field(None, description="Source page URL")
    source_context: Optional[str] = Field(None, max_length=500, description="Surrounding context")
    
    # Classification
    email_type: EmailType = Field(default=EmailType.UNKNOWN, description="Email type classification")
    is_obfuscated: bool = Field(default=False, description="Whether email was obfuscated")
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Discovery confidence")
    
    # Verification results
    verification_level: VerificationLevel = Field(default=VerificationLevel.SYNTAX_ONLY, description="Verification level performed")
    verification_status: VerificationStatus = Field(default=VerificationStatus.UNKNOWN, description="Verification result")
    verification_details: Dict[str, Any] = Field(default_factory=dict, description="Detailed verification results")
    
    # Quality indicators
    domain_reputation_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Domain reputation score")
    deliverability_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Deliverability score")
    
    # Discovery metadata
    discovered_at: datetime = Field(default_factory=datetime.utcnow, description="Discovery timestamp")
    last_verified_at: Optional[datetime] = Field(None, description="Last verification timestamp")
    
    @validator('email_address')
    def validate_email_format(cls, v: str) -> str:
        """Validate email address format."""
        import re
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        if not email_pattern.match(v):
            raise ValueError("Invalid email address format")
        return v.lower().strip()
    
    @validator('source_context', pre=True)
    def clean_source_context(cls, v: Optional[str]) -> Optional[str]:
        """Clean source context text."""
        if v is None:
            return None
        cleaned = v.replace('\x00', '').strip()
        return cleaned if cleaned else None
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            HttpUrl: str
        }
        validate_assignment = True


class VerificationResult(BaseModel):
    """Email verification result with detailed information."""
    
    email_address: str = Field(..., description="Verified email address")
    verification_level: VerificationLevel = Field(..., description="Verification level performed")
    status: VerificationStatus = Field(..., description="Overall verification status")
    
    # Detailed results by verification level
    syntax_valid: bool = Field(..., description="Syntax validation result")
    domain_exists: Optional[bool] = Field(None, description="Domain existence check")
    mx_records_exist: Optional[bool] = Field(None, description="MX records existence")
    mx_records: List[str] = Field(default_factory=list, description="MX record hostnames")
    
    # SMTP verification results
    smtp_connectable: Optional[bool] = Field(None, description="SMTP server connectivity")
    smtp_accepts_mail: Optional[bool] = Field(None, description="SMTP accepts mail for address")
    smtp_response_code: Optional[int] = Field(None, description="SMTP response code")
    smtp_response_message: Optional[str] = Field(None, description="SMTP response message")
    
    # Deliverability indicators
    spf_record_exists: Optional[bool] = Field(None, description="SPF record presence")
    dmarc_record_exists: Optional[bool] = Field(None, description="DMARC record presence")
    is_disposable_domain: bool = Field(default=False, description="Disposable email domain flag")
    is_role_based: bool = Field(default=False, description="Role-based email flag")
    
    # Performance metadata
    verification_duration_ms: float = Field(..., ge=0.0, description="Verification duration in milliseconds")
    verified_at: datetime = Field(default_factory=datetime.utcnow, description="Verification timestamp")
    error_message: Optional[str] = Field(None, description="Error message if verification failed")
    
    @validator('mx_records', pre=True)
    def clean_mx_records(cls, v: Any) -> List[str]:
        """Clean MX records list."""
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return [str(record).strip() for record in v if record]
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class QualityScore(BaseModel):
    """Email quality assessment with multiple dimensions."""
    
    email_address: str = Field(..., description="Assessed email address")
    
    # Quality dimensions
    deliverability_score: float = Field(..., ge=0.0, le=1.0, description="Deliverability likelihood")
    engagement_score: float = Field(..., ge=0.0, le=1.0, description="Engagement potential")
    reputation_score: float = Field(..., ge=0.0, le=1.0, description="Domain reputation")
    authenticity_score: float = Field(..., ge=0.0, le=1.0, description="Email authenticity")
    
    # Composite scores
    overall_quality: float = Field(..., ge=0.0, le=1.0, description="Weighted overall quality")
    risk_level: str = Field(..., description="Risk level assessment")
    
    # Quality factors
    quality_factors: Dict[str, float] = Field(default_factory=dict, description="Individual quality factors")
    risk_factors: List[str] = Field(default_factory=list, description="Identified risk factors")
    positive_signals: List[str] = Field(default_factory=list, description="Positive quality signals")
    
    # Scoring metadata
    scoring_model_version: str = Field(default="1.0", description="Scoring model version")
    scored_at: datetime = Field(default_factory=datetime.utcnow, description="Scoring timestamp")
    
    @validator('risk_level')
    def validate_risk_level(cls, v: str) -> str:
        """Validate risk level values."""
        valid_levels = ['low', 'medium', 'high', 'critical']
        if v.lower() not in valid_levels:
            raise ValueError(f"Risk level must be one of: {valid_levels}")
        return v.lower()
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class ComplianceStatus(BaseModel):
    """GDPR and CAN-SPAM compliance status assessment."""
    
    domain: str = Field(..., description="Assessed domain")
    
    # Compliance flags
    compliance_flags: List[ComplianceFlag] = Field(default_factory=list, description="Detected compliance indicators")
    privacy_policy_url: Optional[HttpUrl] = Field(None, description="Privacy policy URL if found")
    terms_of_service_url: Optional[HttpUrl] = Field(None, description="Terms of service URL if found")
    contact_page_url: Optional[HttpUrl] = Field(None, description="Contact page URL if found")
    
    # GDPR indicators
    gdpr_compliant_indicators: List[str] = Field(default_factory=list, description="GDPR compliance indicators")
    data_processing_basis: Optional[str] = Field(None, description="Legal basis for data processing")
    
    # CAN-SPAM indicators
    can_spam_indicators: List[str] = Field(default_factory=list, description="CAN-SPAM compliance indicators")
    unsubscribe_mechanism: Optional[str] = Field(None, description="Unsubscribe mechanism description")
    
    # Compliance assessment
    compliance_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall compliance score")
    compliance_notes: List[str] = Field(default_factory=list, description="Compliance assessment notes")
    
    # Assessment metadata
    assessed_at: datetime = Field(default_factory=datetime.utcnow, description="Assessment timestamp")
    assessment_version: str = Field(default="1.0", description="Assessment methodology version")
    
    @validator('compliance_notes', pre=True)
    def clean_compliance_notes(cls, v: Any) -> List[str]:
        """Clean compliance notes list."""
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return [str(note).strip() for note in v if note and str(note).strip()]
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            HttpUrl: str
        }
        validate_assignment = True


class EmailDiscoveryResult(BaseModel):
    """Complete email discovery result for a domain."""
    
    domain: str = Field(..., description="Discovered domain")
    base_url: HttpUrl = Field(..., description="Base URL used for discovery")
    
    # Discovery results
    email_candidates: List[EmailCandidate] = Field(default_factory=list, description="Discovered email candidates")
    generated_patterns: List[str] = Field(default_factory=list, description="Generated email patterns")
    
    # Pages crawled
    pages_crawled: List[str] = Field(default_factory=list, description="URLs of pages crawled")
    crawl_depth: int = Field(default=1, ge=1, description="Maximum crawl depth reached")
    
    # Quality and compliance
    overall_quality_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Overall domain quality")
    compliance_status: Optional[ComplianceStatus] = Field(None, description="Compliance assessment")
    
    # Discovery metadata
    discovery_duration_seconds: float = Field(..., ge=0.0, description="Total discovery duration")
    discovered_at: datetime = Field(default_factory=datetime.utcnow, description="Discovery timestamp")
    success: bool = Field(default=True, description="Discovery success status")
    error_message: Optional[str] = Field(None, description="Error message if discovery failed")
    
    # Statistics
    total_candidates_found: int = Field(default=0, ge=0, description="Total candidates discovered")
    verified_candidates: int = Field(default=0, ge=0, description="Number of verified candidates")
    high_quality_candidates: int = Field(default=0, ge=0, description="High quality candidates")
    
    @validator('total_candidates_found')
    def validate_total_candidates(cls, v: int, values: Dict[str, Any]) -> int:
        """Validate total candidates matches actual count."""
        email_candidates = values.get('email_candidates', [])
        if isinstance(email_candidates, list):
            return len(email_candidates)
        return v
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True


# Multi-Source Lead Discovery Models for Prompt 5

class LeadSourceType(str, Enum):
    """Lead source type enumeration."""
    WEB_SEARCH = "web_search"
    GITHUB = "github"
    PRODUCT_HUNT = "product_hunt"
    ANGELLIST = "angellist"
    CRUNCHBASE = "crunchbase"
    F6S = "f6s"
    GUST = "gust"
    USPTO_PATENTS = "uspto_patents"
    GOOGLE_PATENTS = "google_patents"
    JOB_BOARDS = "job_boards"
    LINKEDIN_JOBS = "linkedin_jobs"
    INDEED = "indeed"
    GLASSDOOR = "glassdoor"


class LeadConfidence(str, Enum):
    """Lead confidence level enumeration."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class Lead(BaseModel):
    """Individual lead from a specific source."""
    
    company_name: str = Field(..., min_length=1, max_length=200, description="Company name")
    company_url: Optional[HttpUrl] = Field(None, description="Company website URL")
    domain: Optional[str] = Field(None, max_length=253, description="Normalized domain")
    description: Optional[str] = Field(None, max_length=2000, description="Company description")
    industry_tags: List[str] = Field(default_factory=list, max_items=20, description="Industry classification tags")
    technology_tags: List[str] = Field(default_factory=list, max_items=30, description="Technology stack indicators")
    
    # Source-specific metadata
    source_type: LeadSourceType = Field(..., description="Lead source type")
    source_id: Optional[str] = Field(None, max_length=100, description="Source-specific identifier")
    source_url: Optional[HttpUrl] = Field(None, description="Source page URL")
    source_metadata: Dict[str, Any] = Field(default_factory=dict, description="Source-specific metadata")
    
    # Lead quality indicators
    confidence_level: LeadConfidence = Field(default=LeadConfidence.MEDIUM, description="Lead confidence level")
    relevance_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Relevance score")
    
    # Contact information
    contact_emails: List[str] = Field(default_factory=list, max_items=10, description="Contact email addresses")
    contact_phones: List[str] = Field(default_factory=list, max_items=5, description="Contact phone numbers")
    social_profiles: Dict[str, str] = Field(default_factory=dict, description="Social media profiles")
    
    # Geographic information
    country: Optional[str] = Field(None, max_length=2, description="ISO country code")
    region: Optional[str] = Field(None, max_length=100, description="Geographic region")
    city: Optional[str] = Field(None, max_length=100, description="City location")
    
    # Discovery metadata
    discovered_at: datetime = Field(default_factory=datetime.utcnow, description="Discovery timestamp")
    discovery_query: Optional[str] = Field(None, max_length=500, description="Search query used for discovery")
    
    @validator('domain', pre=True)
    def normalize_domain(cls, v: Optional[str]) -> Optional[str]:
        """Normalize domain to lowercase without www prefix."""
        if not v:
            return None
        
        domain = v.lower().strip()
        if domain.startswith('www.'):
            domain = domain[4:]
        
        return domain if domain else None
    
    @validator('industry_tags', 'technology_tags', pre=True)
    def clean_tag_lists(cls, v: Any) -> List[str]:
        """Clean and validate tag lists."""
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        
        cleaned_tags = []
        for tag in v:
            if isinstance(tag, str) and tag.strip():
                clean_tag = tag.strip().lower()[:50]
                if clean_tag and clean_tag not in cleaned_tags:
                    cleaned_tags.append(clean_tag)
        
        return cleaned_tags
    
    @validator('contact_emails', pre=True)
    def validate_emails(cls, v: Any) -> List[str]:
        """Validate email addresses."""
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        
        valid_emails = []
        for email in v:
            if isinstance(email, str) and '@' in email and '.' in email:
                clean_email = email.strip().lower()
                if clean_email and clean_email not in valid_emails:
                    valid_emails.append(clean_email)
        
        return valid_emails
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True


class LeadSource(BaseModel):
    """Lead source configuration and metadata."""
    
    source_type: LeadSourceType = Field(..., description="Source type identifier")
    source_name: str = Field(..., min_length=1, max_length=100, description="Human-readable source name")
    enabled: bool = Field(default=True, description="Whether source is enabled")
    
    # API configuration
    api_key: Optional[str] = Field(None, description="API key for authenticated sources")
    api_endpoint: Optional[HttpUrl] = Field(None, description="API endpoint URL")
    rate_limit_requests: int = Field(default=60, ge=1, description="Requests per minute limit")
    rate_limit_window: int = Field(default=60, ge=10, description="Rate limit window in seconds")
    
    # Search configuration
    search_keywords: List[str] = Field(default_factory=list, description="Default search keywords")
    search_categories: List[str] = Field(default_factory=list, description="Search categories")
    max_results_per_query: int = Field(default=50, ge=1, le=500, description="Maximum results per query")
    
    # Quality configuration
    min_confidence_threshold: float = Field(default=0.3, ge=0.0, le=1.0, description="Minimum confidence threshold")
    quality_filters: Dict[str, Any] = Field(default_factory=dict, description="Source-specific quality filters")
    
    # Operational metadata
    last_successful_run: Optional[datetime] = Field(None, description="Last successful discovery run")
    last_error: Optional[str] = Field(None, max_length=1000, description="Last error message")
    total_leads_discovered: int = Field(default=0, ge=0, description="Total leads discovered")
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Success rate percentage")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            HttpUrl: str
        }
        validate_assignment = True


class UnifiedLead(BaseModel):
    """Unified lead aggregated from multiple sources."""
    
    # Core company information
    company_name: str = Field(..., min_length=1, max_length=200, description="Resolved company name")
    primary_domain: str = Field(..., min_length=1, max_length=253, description="Primary company domain")
    company_url: HttpUrl = Field(..., description="Primary company website")
    
    # Aggregated descriptions and tags
    description: Optional[str] = Field(None, max_length=2000, description="Merged company description")
    industry_tags: List[str] = Field(default_factory=list, description="Aggregated industry tags")
    technology_tags: List[str] = Field(default_factory=list, description="Aggregated technology tags")
    
    # Source attribution
    source_leads: List[Lead] = Field(..., min_items=1, description="Source leads that contributed to this unified lead")
    primary_source: LeadSourceType = Field(..., description="Primary source with highest confidence")
    source_count: int = Field(..., ge=1, description="Number of contributing sources")
    
    # Aggregated quality metrics
    overall_confidence: LeadConfidence = Field(..., description="Overall confidence level")
    average_relevance_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Average relevance score")
    source_diversity_score: float = Field(..., ge=0.0, le=1.0, description="Source diversity score")
    
    # Contact information (aggregated)
    contact_emails: List[str] = Field(default_factory=list, description="Aggregated contact emails")
    contact_phones: List[str] = Field(default_factory=list, description="Aggregated contact phones")
    social_profiles: Dict[str, str] = Field(default_factory=dict, description="Aggregated social profiles")
    
    # Geographic information
    country: Optional[str] = Field(None, max_length=2, description="Primary country")
    region: Optional[str] = Field(None, max_length=100, description="Primary region")
    city: Optional[str] = Field(None, max_length=100, description="Primary city")
    
    # Aggregation metadata
    aggregated_at: datetime = Field(default_factory=datetime.utcnow, description="Aggregation timestamp")
    deduplication_key: str = Field(..., min_length=1, description="Deduplication key")
    
    @validator('source_count')
    def validate_source_count(cls, v: int, values: Dict[str, Any]) -> int:
        """Validate source count matches actual sources."""
        source_leads = values.get('source_leads', [])
        if isinstance(source_leads, list):
            return len(source_leads)
        return v
    
    @validator('source_diversity_score')
    def calculate_diversity_score(cls, v: float, values: Dict[str, Any]) -> float:
        """Calculate source diversity score."""
        source_leads = values.get('source_leads', [])
        if not isinstance(source_leads, list) or not source_leads:
            return 0.0
        
        unique_sources = len(set(lead.source_type for lead in source_leads))
        max_possible_sources = len(LeadSourceType)
        return min(unique_sources / max_possible_sources, 1.0)
    
    @validator('deduplication_key')
    def generate_deduplication_key(cls, v: str, values: Dict[str, Any]) -> str:
        """Generate deduplication key from domain."""
        primary_domain = values.get('primary_domain', '')
        if primary_domain:
            return primary_domain.lower()
        return v
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True


class DiscoveryBatch(BaseModel):
    """Batch discovery execution model."""
    
    batch_id: str = Field(..., min_length=1, description="Unique batch identifier")
    enabled_sources: List[LeadSourceType] = Field(..., min_items=1, description="Enabled source types")
    search_keywords: List[str] = Field(..., min_items=1, description="Search keywords")
    search_categories: List[str] = Field(default_factory=list, description="Search categories")
    
    # Execution parameters
    max_leads_per_source: int = Field(default=100, ge=1, le=1000, description="Maximum leads per source")
    timeout_seconds: int = Field(default=7200, ge=300, le=14400, description="Total batch timeout")
    concurrent_sources: int = Field(default=4, ge=1, le=10, description="Concurrent source limit")
    
    # Quality filters
    min_confidence_level: LeadConfidence = Field(default=LeadConfidence.LOW, description="Minimum confidence level")
    duplicate_threshold: float = Field(default=0.9, ge=0.5, le=1.0, description="Duplicate detection threshold")
    
    # Execution metadata
    started_at: Optional[datetime] = Field(None, description="Batch start time")
    completed_at: Optional[datetime] = Field(None, description="Batch completion time")
    status: SearchStatus = Field(default=SearchStatus.PENDING, description="Batch execution status")
    
    # Results
    total_leads_discovered: int = Field(default=0, ge=0, description="Total leads discovered")
    unified_leads_created: int = Field(default=0, ge=0, description="Unified leads created")
    duplicate_leads_filtered: int = Field(default=0, ge=0, description="Duplicate leads filtered")
    failed_sources: List[str] = Field(default_factory=list, description="Failed source names")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
        validate_assignment = True


class DiscoveryResult(BaseModel):
    """Complete discovery result model."""
    
    batch: DiscoveryBatch = Field(..., description="Batch configuration and metadata")
    unified_leads: List[UnifiedLead] = Field(default_factory=list, description="Discovered unified leads")
    source_results: Dict[str, List[Lead]] = Field(default_factory=dict, description="Raw results by source")
    
    # Performance metrics
    execution_time_seconds: float = Field(default=0.0, ge=0.0, description="Total execution time")
    leads_per_second: float = Field(default=0.0, ge=0.0, description="Discovery rate")
    source_success_rates: Dict[str, float] = Field(default_factory=dict, description="Success rates by source")
    
    # Quality metrics
    duplicate_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Duplicate rate percentage")
    average_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Average confidence score")
    source_diversity: float = Field(default=0.0, ge=0.0, le=1.0, description="Source diversity score")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
        validate_assignment = True