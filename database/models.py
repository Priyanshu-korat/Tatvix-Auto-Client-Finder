"""Data models for duplicate detection system.

This module defines Pydantic models for duplicate detection results,
similarity scoring, audit trail functionality, and vector database operations.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field, validator, HttpUrl
import uuid


def generate_default_email(website: Union[str, HttpUrl]) -> str:
    """Generate default email address from website domain.
    
    Args:
        website: Website URL
        
    Returns:
        Generated email address using info@ pattern
    """
    domain = str(website).replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
    return f"info@{domain}"


class DuplicateLevel(str, Enum):
    """Duplicate detection level enumeration."""
    LEVEL_1_DOMAIN = "level_1_domain"
    LEVEL_2_EMBEDDING = "level_2_embedding"
    LEVEL_3_BUSINESS_LOGIC = "level_3_business_logic"


class DuplicateDecisionType(str, Enum):
    """Duplicate decision type enumeration."""
    DUPLICATE = "duplicate"
    SIMILAR = "similar"
    UNIQUE = "unique"


class SimilarityMetrics(BaseModel):
    """Detailed similarity metrics for company comparison."""
    
    domain_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Domain similarity score")
    name_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Company name similarity score")
    description_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Description similarity score")
    location_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Location similarity score")
    phone_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Phone similarity score")
    technology_overlap: float = Field(default=0.0, ge=0.0, le=1.0, description="Technology stack overlap score")
    embedding_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Vector embedding similarity score")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class LeadStatus(str, Enum):
    """Lead processing status enumeration."""
    NEW = "new"
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    CONVERTED = "converted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    ERROR = "error"


class LeadData(BaseModel):
    """Lead data model for Google Sheets storage.
    
    Represents a single lead with all required fields for the Tatvix AI
    Client Discovery system, including validation and schema enforcement.
    """
    
    # Core identification
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique lead identifier")
    company: str = Field(..., min_length=2, max_length=100, description="Company name")
    website: HttpUrl = Field(..., description="Company website URL")
    email: Optional[str] = Field(None, max_length=254, description="Primary contact email")
    
    # Geographic and industry information
    country: str = Field(..., min_length=2, max_length=3, description="ISO country code")
    industry: str = Field(..., min_length=2, max_length=100, description="Business industry category")
    
    # Scoring and status
    score: int = Field(..., ge=1, le=10, description="Lead quality score (1-10)")
    status: LeadStatus = Field(default=LeadStatus.NEW, description="Current processing status")
    source: str = Field(..., min_length=1, max_length=50, description="Discovery source attribution")
    
    # Personalized outreach content
    personalized_email: Optional[str] = Field(None, description="AI-generated personalized email content")
    email_subject: Optional[str] = Field(None, max_length=200, description="Personalized email subject line")
    
    # Timestamps
    created: datetime = Field(default_factory=datetime.utcnow, description="Lead discovery timestamp")
    updated: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    
    @validator('email')
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate email format if provided."""
        if v is None:
            return v
        
        # Basic email validation
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")
        
        return v.lower().strip()
    
    @validator('country')
    def validate_country_code(cls, v: str) -> str:
        """Validate country code format."""
        v = v.upper().strip()
        if len(v) not in [2, 3]:
            raise ValueError("Country code must be 2 or 3 characters (ISO format)")
        return v
    
    @validator('company')
    def validate_company_name(cls, v: str) -> str:
        """Validate and clean company name."""
        v = v.strip()
        if not v:
            raise ValueError("Company name cannot be empty")
        
        # Remove excessive whitespace
        v = ' '.join(v.split())
        return v
    
    @validator('industry')
    def validate_industry_category(cls, v: str) -> str:
        """Validate industry category."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Industry category cannot be empty")
        return v
    
    @validator('source')
    def validate_source_attribution(cls, v: str) -> str:
        """Validate source attribution."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Source attribution cannot be empty")
        return v
    
    @validator('updated', pre=True, always=True)
    def set_updated_timestamp(cls, v: Any) -> datetime:
        """Ensure updated timestamp is always current."""
        return datetime.utcnow()
    
    def to_sheets_row(self) -> List[str]:
        """Convert lead data to Google Sheets row format matching user's sheet structure.
        
        Returns:
            List of string values for spreadsheet insertion in format:
            [Lead Found Date, Company Name, Website, Industry, Location, Subject, Email, Email Address]
        """
        from datetime import datetime
        
        # Format date as DD/MM/YYYY to match user's format
        lead_found_date = datetime.now().strftime('%d/%m/%Y')
        
        # Create location string (City, Country format)
        location = f"Global, {self.country}" if self.country else "Global"
        
        # Use personalized subject or create default
        subject = self.email_subject or f"Engineering partnership opportunities with {self.company}"
        
        # Use personalized email content or create default
        email_content = self.personalized_email or f"""Hello,

I recently came across {self.company} and your work in the {self.industry} space. Your approach to building innovative solutions is impressive.

At Tatvix Technologies we work with companies building connected hardware systems where embedded firmware, device connectivity, and backend infrastructure need to operate together reliably. Our team often supports engineering groups working on IoT telemetry platforms, device monitoring dashboards, and backend systems for distributed hardware infrastructure.

If your team ever needs additional engineering bandwidth around device connectivity, embedded systems, or infrastructure monitoring platforms, we would be glad to explore whether we could support your development efforts."""
        
        # Generate email address from domain
        email_address = self.email or generate_default_email(self.website)
        
        return [
            lead_found_date,        # Lead Found Date
            self.company,           # Company Name  
            str(self.website),      # Website
            self.industry,          # Industry
            location,               # Location (City, Country)
            subject,                # Subject
            email_content,          # Email (personalized content)
            email_address           # Email Address
        ]
    
    @classmethod
    def from_sheets_row(cls, row: List[str]) -> 'LeadData':
        """Create LeadData instance from Google Sheets row.
        
        Args:
            row: List of string values from spreadsheet.
            
        Returns:
            LeadData instance.
            
        Raises:
            ValueError: If row data is invalid or incomplete.
        """
        if len(row) < 11:
            raise ValueError(f"Insufficient row data: expected 11 columns, got {len(row)}")
        
        try:
            return cls(
                id=row[0] if row[0] else str(uuid.uuid4()),
                company=row[1],
                website=row[2],
                email=row[3] if row[3] else None,
                country=row[4],
                industry=row[5],
                score=int(row[6]),
                status=LeadStatus(row[7]) if row[7] else LeadStatus.NEW,
                source=row[8],
                created=datetime.fromisoformat(row[9]) if row[9] else datetime.utcnow(),
                updated=datetime.fromisoformat(row[10]) if row[10] else datetime.utcnow()
            )
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid row data format: {e}")
    
    @classmethod
    def get_headers(cls) -> List[str]:
        """Get column headers for Google Sheets.
        
        Returns:
            List of column header names.
        """
        return [
            "ID",
            "Company", 
            "Website",
            "Email",
            "Country",
            "Industry",
            "Score",
            "Status",
            "Source",
            "Created",
            "Updated"
        ]
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True
        use_enum_values = True


class SheetsOperationResult(BaseModel):
    """Result model for Google Sheets operations."""
    
    success: bool = Field(..., description="Operation success status")
    operation_type: str = Field(..., description="Type of operation performed")
    rows_affected: int = Field(default=0, ge=0, description="Number of rows affected")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Operation duration in milliseconds")
    
    # Optional result data
    data: Optional[List[Dict[str, Any]]] = Field(None, description="Operation result data")
    error_message: Optional[str] = Field(None, description="Error message if operation failed")
    
    # Metadata
    spreadsheet_id: Optional[str] = Field(None, description="Google Sheets spreadsheet ID")
    worksheet_name: Optional[str] = Field(None, description="Worksheet name")
    range_updated: Optional[str] = Field(None, description="Range that was updated")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class BackupResult(BaseModel):
    """Result model for backup operations."""
    
    success: bool = Field(..., description="Backup success status")
    backup_path: str = Field(..., description="Path to backup file")
    backup_format: str = Field(..., description="Backup file format (csv, json)")
    rows_exported: int = Field(default=0, ge=0, description="Number of rows exported")
    file_size_bytes: int = Field(default=0, ge=0, description="Backup file size in bytes")
    
    # Timestamps
    backup_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Backup creation timestamp")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Backup operation duration")
    
    # Optional error information
    error_message: Optional[str] = Field(None, description="Error message if backup failed")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class SimilarCompany(BaseModel):
    """Similar company result from duplicate detection."""
    
    company_id: str = Field(..., min_length=1, description="Unique company identifier")
    company_name: str = Field(..., min_length=1, max_length=200, description="Company name")
    company_url: Optional[HttpUrl] = Field(None, description="Company website URL")
    domain: str = Field(..., min_length=1, max_length=253, description="Normalized domain")
    
    # Similarity scores
    similarity_metrics: SimilarityMetrics = Field(..., description="Detailed similarity metrics")
    overall_similarity: float = Field(..., ge=0.0, le=1.0, description="Weighted overall similarity score")
    
    # Detection metadata
    detection_level: DuplicateLevel = Field(..., description="Detection level that found this match")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Detection confidence score")
    
    # Matching details
    matched_fields: List[str] = Field(default_factory=list, description="Fields that contributed to the match")
    match_reason: str = Field(..., min_length=1, max_length=500, description="Human-readable match explanation")
    
    # Metadata
    detected_at: datetime = Field(default_factory=datetime.utcnow, description="Detection timestamp")
    
    @validator('matched_fields', pre=True)
    def clean_matched_fields(cls, v: Any) -> List[str]:
        """Clean matched fields list."""
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return [str(field).strip() for field in v if field and str(field).strip()]
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True


class DuplicateDecision(BaseModel):
    """Duplicate detection decision with audit trail."""
    
    decision_id: str = Field(..., min_length=1, description="Unique decision identifier")
    incoming_company_id: str = Field(..., min_length=1, description="Incoming company identifier")
    incoming_domain: str = Field(..., min_length=1, description="Incoming company domain")
    
    # Decision result
    decision_type: DuplicateDecisionType = Field(..., description="Final duplicate decision")
    is_duplicate: bool = Field(..., description="Whether company is considered duplicate")
    
    # Similar companies found
    similar_companies: List[SimilarCompany] = Field(default_factory=list, description="Similar companies found")
    best_match: Optional[SimilarCompany] = Field(None, description="Best matching company if any")
    
    # Detection details
    levels_checked: List[DuplicateLevel] = Field(..., min_items=1, description="Detection levels that were checked")
    triggered_level: Optional[DuplicateLevel] = Field(None, description="Level that triggered the duplicate decision")
    
    # Scoring details
    similarity_threshold_used: float = Field(..., ge=0.0, le=1.0, description="Similarity threshold used")
    max_similarity_found: float = Field(default=0.0, ge=0.0, le=1.0, description="Maximum similarity score found")
    
    # Processing metadata
    processing_duration_ms: float = Field(..., ge=0.0, description="Processing duration in milliseconds")
    checked_companies_count: int = Field(default=0, ge=0, description="Number of companies checked")
    
    # Audit information
    decision_reasoning: str = Field(..., min_length=1, max_length=1000, description="Decision reasoning")
    configuration_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Configuration used")
    decided_at: datetime = Field(default_factory=datetime.utcnow, description="Decision timestamp")
    
    @validator('levels_checked', pre=True)
    def validate_levels_checked(cls, v: Any) -> List[DuplicateLevel]:
        """Validate levels checked list."""
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        
        valid_levels = []
        for level in v:
            if isinstance(level, str):
                try:
                    valid_levels.append(DuplicateLevel(level))
                except ValueError:
                    continue
            elif isinstance(level, DuplicateLevel):
                valid_levels.append(level)
        
        return valid_levels if valid_levels else [DuplicateLevel.LEVEL_1_DOMAIN]
    
    @validator('best_match')
    def validate_best_match(cls, v: Optional[SimilarCompany], values: Dict[str, Any]) -> Optional[SimilarCompany]:
        """Validate best match selection."""
        similar_companies = values.get('similar_companies', [])
        if not similar_companies:
            return None
        
        if v is None:
            # Auto-select best match if not provided
            return max(similar_companies, key=lambda x: x.overall_similarity)
        
        return v
    
    @validator('max_similarity_found')
    def calculate_max_similarity(cls, v: float, values: Dict[str, Any]) -> float:
        """Calculate maximum similarity from similar companies."""
        similar_companies = values.get('similar_companies', [])
        if not similar_companies:
            return v
        
        return max(company.overall_similarity for company in similar_companies)
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class DuplicateCheckRequest(BaseModel):
    """Request model for duplicate checking."""
    
    company_data: Dict[str, Any] = Field(..., description="Company data to check for duplicates")
    check_levels: List[DuplicateLevel] = Field(
        default_factory=lambda: [DuplicateLevel.LEVEL_1_DOMAIN, DuplicateLevel.LEVEL_3_BUSINESS_LOGIC, DuplicateLevel.LEVEL_2_EMBEDDING],
        description="Detection levels to check in order"
    )
    similarity_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Override similarity threshold")
    max_similar_companies: int = Field(default=10, ge=1, le=100, description="Maximum similar companies to return")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class LeadStatus(str, Enum):
    """Lead processing status enumeration."""
    NEW = "new"
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    CONVERTED = "converted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    ERROR = "error"


class LeadData(BaseModel):
    """Lead data model for Google Sheets storage.
    
    Represents a single lead with all required fields for the Tatvix AI
    Client Discovery system, including validation and schema enforcement.
    """
    
    # Core identification
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique lead identifier")
    company: str = Field(..., min_length=2, max_length=100, description="Company name")
    website: HttpUrl = Field(..., description="Company website URL")
    email: Optional[str] = Field(None, max_length=254, description="Primary contact email")
    
    # Geographic and industry information
    country: str = Field(..., min_length=2, max_length=3, description="ISO country code")
    industry: str = Field(..., min_length=2, max_length=100, description="Business industry category")
    
    # Scoring and status
    score: int = Field(..., ge=1, le=10, description="Lead quality score (1-10)")
    status: LeadStatus = Field(default=LeadStatus.NEW, description="Current processing status")
    source: str = Field(..., min_length=1, max_length=50, description="Discovery source attribution")
    
    # Personalized outreach content
    personalized_email: Optional[str] = Field(None, description="AI-generated personalized email content")
    email_subject: Optional[str] = Field(None, max_length=200, description="Personalized email subject line")
    
    # Timestamps
    created: datetime = Field(default_factory=datetime.utcnow, description="Lead discovery timestamp")
    updated: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    
    @validator('email')
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate email format if provided."""
        if v is None:
            return v
        
        # Basic email validation
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")
        
        return v.lower().strip()
    
    @validator('country')
    def validate_country_code(cls, v: str) -> str:
        """Validate country code format."""
        v = v.upper().strip()
        if len(v) not in [2, 3]:
            raise ValueError("Country code must be 2 or 3 characters (ISO format)")
        return v
    
    @validator('company')
    def validate_company_name(cls, v: str) -> str:
        """Validate and clean company name."""
        v = v.strip()
        if not v:
            raise ValueError("Company name cannot be empty")
        
        # Remove excessive whitespace
        v = ' '.join(v.split())
        return v
    
    @validator('industry')
    def validate_industry_category(cls, v: str) -> str:
        """Validate industry category."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Industry category cannot be empty")
        return v
    
    @validator('source')
    def validate_source_attribution(cls, v: str) -> str:
        """Validate source attribution."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Source attribution cannot be empty")
        return v
    
    @validator('updated', pre=True, always=True)
    def set_updated_timestamp(cls, v: Any) -> datetime:
        """Ensure updated timestamp is always current."""
        return datetime.utcnow()
    
    def to_sheets_row(self) -> List[str]:
        """Convert lead data to Google Sheets row format matching user's sheet structure.
        
        Returns:
            List of string values for spreadsheet insertion in format:
            [Lead Found Date, Company Name, Website, Industry, Location, Subject, Email, Email Address]
        """
        from datetime import datetime
        
        # Format date as DD/MM/YYYY to match user's format
        lead_found_date = datetime.now().strftime('%d/%m/%Y')
        
        # Create location string (City, Country format)
        location = f"Global, {self.country}" if self.country else "Global"
        
        # Use personalized subject or create default
        subject = self.email_subject or f"Engineering partnership opportunities with {self.company}"
        
        # Use personalized email content or create default
        email_content = self.personalized_email or f"""Hello,

I recently came across {self.company} and your work in the {self.industry} space. Your approach to building innovative solutions is impressive.

At Tatvix Technologies we work with companies building connected hardware systems where embedded firmware, device connectivity, and backend infrastructure need to operate together reliably. Our team often supports engineering groups working on IoT telemetry platforms, device monitoring dashboards, and backend systems for distributed hardware infrastructure.

If your team ever needs additional engineering bandwidth around device connectivity, embedded systems, or infrastructure monitoring platforms, we would be glad to explore whether we could support your development efforts."""
        
        # Generate email address from domain
        email_address = self.email or generate_default_email(self.website)
        
        return [
            lead_found_date,        # Lead Found Date
            self.company,           # Company Name  
            str(self.website),      # Website
            self.industry,          # Industry
            location,               # Location (City, Country)
            subject,                # Subject
            email_content,          # Email (personalized content)
            email_address           # Email Address
        ]
    
    @classmethod
    def from_sheets_row(cls, row: List[str]) -> 'LeadData':
        """Create LeadData instance from Google Sheets row.
        
        Args:
            row: List of string values from spreadsheet.
            
        Returns:
            LeadData instance.
            
        Raises:
            ValueError: If row data is invalid or incomplete.
        """
        if len(row) < 11:
            raise ValueError(f"Insufficient row data: expected 11 columns, got {len(row)}")
        
        try:
            return cls(
                id=row[0] if row[0] else str(uuid.uuid4()),
                company=row[1],
                website=row[2],
                email=row[3] if row[3] else None,
                country=row[4],
                industry=row[5],
                score=int(row[6]),
                status=LeadStatus(row[7]) if row[7] else LeadStatus.NEW,
                source=row[8],
                created=datetime.fromisoformat(row[9]) if row[9] else datetime.utcnow(),
                updated=datetime.fromisoformat(row[10]) if row[10] else datetime.utcnow()
            )
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid row data format: {e}")
    
    @classmethod
    def get_headers(cls) -> List[str]:
        """Get column headers for Google Sheets.
        
        Returns:
            List of column header names.
        """
        return [
            "ID",
            "Company", 
            "Website",
            "Email",
            "Country",
            "Industry",
            "Score",
            "Status",
            "Source",
            "Created",
            "Updated"
        ]
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True
        use_enum_values = True


class SheetsOperationResult(BaseModel):
    """Result model for Google Sheets operations."""
    
    success: bool = Field(..., description="Operation success status")
    operation_type: str = Field(..., description="Type of operation performed")
    rows_affected: int = Field(default=0, ge=0, description="Number of rows affected")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Operation duration in milliseconds")
    
    # Optional result data
    data: Optional[List[Dict[str, Any]]] = Field(None, description="Operation result data")
    error_message: Optional[str] = Field(None, description="Error message if operation failed")
    
    # Metadata
    spreadsheet_id: Optional[str] = Field(None, description="Google Sheets spreadsheet ID")
    worksheet_name: Optional[str] = Field(None, description="Worksheet name")
    range_updated: Optional[str] = Field(None, description="Range that was updated")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class BackupResult(BaseModel):
    """Result model for backup operations."""
    
    success: bool = Field(..., description="Backup success status")
    backup_path: str = Field(..., description="Path to backup file")
    backup_format: str = Field(..., description="Backup file format (csv, json)")
    rows_exported: int = Field(default=0, ge=0, description="Number of rows exported")
    file_size_bytes: int = Field(default=0, ge=0, description="Backup file size in bytes")
    
    # Timestamps
    backup_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Backup creation timestamp")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Backup operation duration")
    
    # Optional error information
    error_message: Optional[str] = Field(None, description="Error message if backup failed")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class DuplicateCheckResponse(BaseModel):
    """Response model for duplicate checking."""
    
    success: bool = Field(..., description="Check success status")
    decision: Optional[DuplicateDecision] = Field(None, description="Duplicate decision if successful")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    # Performance metadata
    total_duration_ms: float = Field(default=0.0, ge=0.0, description="Total check duration")
    cache_hit: bool = Field(default=False, description="Whether result was cached")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class LeadStatus(str, Enum):
    """Lead processing status enumeration."""
    NEW = "new"
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    CONVERTED = "converted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    ERROR = "error"


class LeadData(BaseModel):
    """Lead data model for Google Sheets storage.
    
    Represents a single lead with all required fields for the Tatvix AI
    Client Discovery system, including validation and schema enforcement.
    """
    
    # Core identification
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique lead identifier")
    company: str = Field(..., min_length=2, max_length=100, description="Company name")
    website: HttpUrl = Field(..., description="Company website URL")
    email: Optional[str] = Field(None, max_length=254, description="Primary contact email")
    
    # Geographic and industry information
    country: str = Field(..., min_length=2, max_length=3, description="ISO country code")
    industry: str = Field(..., min_length=2, max_length=100, description="Business industry category")
    
    # Scoring and status
    score: int = Field(..., ge=1, le=10, description="Lead quality score (1-10)")
    status: LeadStatus = Field(default=LeadStatus.NEW, description="Current processing status")
    source: str = Field(..., min_length=1, max_length=50, description="Discovery source attribution")
    
    # Personalized outreach content
    personalized_email: Optional[str] = Field(None, description="AI-generated personalized email content")
    email_subject: Optional[str] = Field(None, max_length=200, description="Personalized email subject line")
    
    # Timestamps
    created: datetime = Field(default_factory=datetime.utcnow, description="Lead discovery timestamp")
    updated: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    
    @validator('email')
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate email format if provided."""
        if v is None:
            return v
        
        # Basic email validation
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")
        
        return v.lower().strip()
    
    @validator('country')
    def validate_country_code(cls, v: str) -> str:
        """Validate country code format."""
        v = v.upper().strip()
        if len(v) not in [2, 3]:
            raise ValueError("Country code must be 2 or 3 characters (ISO format)")
        return v
    
    @validator('company')
    def validate_company_name(cls, v: str) -> str:
        """Validate and clean company name."""
        v = v.strip()
        if not v:
            raise ValueError("Company name cannot be empty")
        
        # Remove excessive whitespace
        v = ' '.join(v.split())
        return v
    
    @validator('industry')
    def validate_industry_category(cls, v: str) -> str:
        """Validate industry category."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Industry category cannot be empty")
        return v
    
    @validator('source')
    def validate_source_attribution(cls, v: str) -> str:
        """Validate source attribution."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Source attribution cannot be empty")
        return v
    
    @validator('updated', pre=True, always=True)
    def set_updated_timestamp(cls, v: Any) -> datetime:
        """Ensure updated timestamp is always current."""
        return datetime.utcnow()
    
    def to_sheets_row(self) -> List[str]:
        """Convert lead data to Google Sheets row format matching user's sheet structure.
        
        Returns:
            List of string values for spreadsheet insertion in format:
            [Lead Found Date, Company Name, Website, Industry, Location, Subject, Email, Email Address]
        """
        from datetime import datetime
        
        # Format date as DD/MM/YYYY to match user's format
        lead_found_date = datetime.now().strftime('%d/%m/%Y')
        
        # Create location string (City, Country format)
        location = f"Global, {self.country}" if self.country else "Global"
        
        # Use personalized subject or create default
        subject = self.email_subject or f"Engineering partnership opportunities with {self.company}"
        
        # Use personalized email content or create default
        email_content = self.personalized_email or f"""Hello,

I recently came across {self.company} and your work in the {self.industry} space. Your approach to building innovative solutions is impressive.

At Tatvix Technologies we work with companies building connected hardware systems where embedded firmware, device connectivity, and backend infrastructure need to operate together reliably. Our team often supports engineering groups working on IoT telemetry platforms, device monitoring dashboards, and backend systems for distributed hardware infrastructure.

If your team ever needs additional engineering bandwidth around device connectivity, embedded systems, or infrastructure monitoring platforms, we would be glad to explore whether we could support your development efforts."""
        
        # Generate email address from domain
        email_address = self.email or generate_default_email(self.website)
        
        return [
            lead_found_date,        # Lead Found Date
            self.company,           # Company Name  
            str(self.website),      # Website
            self.industry,          # Industry
            location,               # Location (City, Country)
            subject,                # Subject
            email_content,          # Email (personalized content)
            email_address           # Email Address
        ]
    
    @classmethod
    def from_sheets_row(cls, row: List[str]) -> 'LeadData':
        """Create LeadData instance from Google Sheets row.
        
        Args:
            row: List of string values from spreadsheet.
            
        Returns:
            LeadData instance.
            
        Raises:
            ValueError: If row data is invalid or incomplete.
        """
        if len(row) < 11:
            raise ValueError(f"Insufficient row data: expected 11 columns, got {len(row)}")
        
        try:
            return cls(
                id=row[0] if row[0] else str(uuid.uuid4()),
                company=row[1],
                website=row[2],
                email=row[3] if row[3] else None,
                country=row[4],
                industry=row[5],
                score=int(row[6]),
                status=LeadStatus(row[7]) if row[7] else LeadStatus.NEW,
                source=row[8],
                created=datetime.fromisoformat(row[9]) if row[9] else datetime.utcnow(),
                updated=datetime.fromisoformat(row[10]) if row[10] else datetime.utcnow()
            )
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid row data format: {e}")
    
    @classmethod
    def get_headers(cls) -> List[str]:
        """Get column headers for Google Sheets.
        
        Returns:
            List of column header names.
        """
        return [
            "ID",
            "Company", 
            "Website",
            "Email",
            "Country",
            "Industry",
            "Score",
            "Status",
            "Source",
            "Created",
            "Updated"
        ]
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True
        use_enum_values = True


class SheetsOperationResult(BaseModel):
    """Result model for Google Sheets operations."""
    
    success: bool = Field(..., description="Operation success status")
    operation_type: str = Field(..., description="Type of operation performed")
    rows_affected: int = Field(default=0, ge=0, description="Number of rows affected")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Operation duration in milliseconds")
    
    # Optional result data
    data: Optional[List[Dict[str, Any]]] = Field(None, description="Operation result data")
    error_message: Optional[str] = Field(None, description="Error message if operation failed")
    
    # Metadata
    spreadsheet_id: Optional[str] = Field(None, description="Google Sheets spreadsheet ID")
    worksheet_name: Optional[str] = Field(None, description="Worksheet name")
    range_updated: Optional[str] = Field(None, description="Range that was updated")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class BackupResult(BaseModel):
    """Result model for backup operations."""
    
    success: bool = Field(..., description="Backup success status")
    backup_path: str = Field(..., description="Path to backup file")
    backup_format: str = Field(..., description="Backup file format (csv, json)")
    rows_exported: int = Field(default=0, ge=0, description="Number of rows exported")
    file_size_bytes: int = Field(default=0, ge=0, description="Backup file size in bytes")
    
    # Timestamps
    backup_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Backup creation timestamp")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Backup operation duration")
    
    # Optional error information
    error_message: Optional[str] = Field(None, description="Error message if backup failed")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class BatchDuplicateCheckRequest(BaseModel):
    """Request model for batch duplicate checking."""
    
    companies_data: List[Dict[str, Any]] = Field(..., min_items=1, description="List of companies to check")
    batch_id: str = Field(..., min_length=1, description="Unique batch identifier")
    
    # Batch configuration
    check_levels: List[DuplicateLevel] = Field(
        default_factory=lambda: [DuplicateLevel.LEVEL_1_DOMAIN, DuplicateLevel.LEVEL_3_BUSINESS_LOGIC, DuplicateLevel.LEVEL_2_EMBEDDING],
        description="Detection levels to check"
    )
    similarity_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Override similarity threshold")
    max_similar_companies: int = Field(default=10, ge=1, le=100, description="Maximum similar companies per check")
    
    # Performance configuration
    max_concurrent_checks: int = Field(default=5, ge=1, le=20, description="Maximum concurrent duplicate checks")
    timeout_seconds: int = Field(default=300, ge=30, le=1800, description="Batch timeout in seconds")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class LeadStatus(str, Enum):
    """Lead processing status enumeration."""
    NEW = "new"
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    CONVERTED = "converted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    ERROR = "error"


class LeadData(BaseModel):
    """Lead data model for Google Sheets storage.
    
    Represents a single lead with all required fields for the Tatvix AI
    Client Discovery system, including validation and schema enforcement.
    """
    
    # Core identification
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique lead identifier")
    company: str = Field(..., min_length=2, max_length=100, description="Company name")
    website: HttpUrl = Field(..., description="Company website URL")
    email: Optional[str] = Field(None, max_length=254, description="Primary contact email")
    
    # Geographic and industry information
    country: str = Field(..., min_length=2, max_length=3, description="ISO country code")
    industry: str = Field(..., min_length=2, max_length=100, description="Business industry category")
    
    # Scoring and status
    score: int = Field(..., ge=1, le=10, description="Lead quality score (1-10)")
    status: LeadStatus = Field(default=LeadStatus.NEW, description="Current processing status")
    source: str = Field(..., min_length=1, max_length=50, description="Discovery source attribution")
    
    # Personalized outreach content
    personalized_email: Optional[str] = Field(None, description="AI-generated personalized email content")
    email_subject: Optional[str] = Field(None, max_length=200, description="Personalized email subject line")
    
    # Timestamps
    created: datetime = Field(default_factory=datetime.utcnow, description="Lead discovery timestamp")
    updated: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    
    @validator('email')
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate email format if provided."""
        if v is None:
            return v
        
        # Basic email validation
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")
        
        return v.lower().strip()
    
    @validator('country')
    def validate_country_code(cls, v: str) -> str:
        """Validate country code format."""
        v = v.upper().strip()
        if len(v) not in [2, 3]:
            raise ValueError("Country code must be 2 or 3 characters (ISO format)")
        return v
    
    @validator('company')
    def validate_company_name(cls, v: str) -> str:
        """Validate and clean company name."""
        v = v.strip()
        if not v:
            raise ValueError("Company name cannot be empty")
        
        # Remove excessive whitespace
        v = ' '.join(v.split())
        return v
    
    @validator('industry')
    def validate_industry_category(cls, v: str) -> str:
        """Validate industry category."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Industry category cannot be empty")
        return v
    
    @validator('source')
    def validate_source_attribution(cls, v: str) -> str:
        """Validate source attribution."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Source attribution cannot be empty")
        return v
    
    @validator('updated', pre=True, always=True)
    def set_updated_timestamp(cls, v: Any) -> datetime:
        """Ensure updated timestamp is always current."""
        return datetime.utcnow()
    
    def to_sheets_row(self) -> List[str]:
        """Convert lead data to Google Sheets row format matching user's sheet structure.
        
        Returns:
            List of string values for spreadsheet insertion in format:
            [Lead Found Date, Company Name, Website, Industry, Location, Subject, Email, Email Address]
        """
        from datetime import datetime
        
        # Format date as DD/MM/YYYY to match user's format
        lead_found_date = datetime.now().strftime('%d/%m/%Y')
        
        # Create location string (City, Country format)
        location = f"Global, {self.country}" if self.country else "Global"
        
        # Use personalized subject or create default
        subject = self.email_subject or f"Engineering partnership opportunities with {self.company}"
        
        # Use personalized email content or create default
        email_content = self.personalized_email or f"""Hello,

I recently came across {self.company} and your work in the {self.industry} space. Your approach to building innovative solutions is impressive.

At Tatvix Technologies we work with companies building connected hardware systems where embedded firmware, device connectivity, and backend infrastructure need to operate together reliably. Our team often supports engineering groups working on IoT telemetry platforms, device monitoring dashboards, and backend systems for distributed hardware infrastructure.

If your team ever needs additional engineering bandwidth around device connectivity, embedded systems, or infrastructure monitoring platforms, we would be glad to explore whether we could support your development efforts."""
        
        # Generate email address from domain
        email_address = self.email or generate_default_email(self.website)
        
        return [
            lead_found_date,        # Lead Found Date
            self.company,           # Company Name  
            str(self.website),      # Website
            self.industry,          # Industry
            location,               # Location (City, Country)
            subject,                # Subject
            email_content,          # Email (personalized content)
            email_address           # Email Address
        ]
    
    @classmethod
    def from_sheets_row(cls, row: List[str]) -> 'LeadData':
        """Create LeadData instance from Google Sheets row.
        
        Args:
            row: List of string values from spreadsheet.
            
        Returns:
            LeadData instance.
            
        Raises:
            ValueError: If row data is invalid or incomplete.
        """
        if len(row) < 11:
            raise ValueError(f"Insufficient row data: expected 11 columns, got {len(row)}")
        
        try:
            return cls(
                id=row[0] if row[0] else str(uuid.uuid4()),
                company=row[1],
                website=row[2],
                email=row[3] if row[3] else None,
                country=row[4],
                industry=row[5],
                score=int(row[6]),
                status=LeadStatus(row[7]) if row[7] else LeadStatus.NEW,
                source=row[8],
                created=datetime.fromisoformat(row[9]) if row[9] else datetime.utcnow(),
                updated=datetime.fromisoformat(row[10]) if row[10] else datetime.utcnow()
            )
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid row data format: {e}")
    
    @classmethod
    def get_headers(cls) -> List[str]:
        """Get column headers for Google Sheets.
        
        Returns:
            List of column header names.
        """
        return [
            "ID",
            "Company", 
            "Website",
            "Email",
            "Country",
            "Industry",
            "Score",
            "Status",
            "Source",
            "Created",
            "Updated"
        ]
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True
        use_enum_values = True


class SheetsOperationResult(BaseModel):
    """Result model for Google Sheets operations."""
    
    success: bool = Field(..., description="Operation success status")
    operation_type: str = Field(..., description="Type of operation performed")
    rows_affected: int = Field(default=0, ge=0, description="Number of rows affected")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Operation duration in milliseconds")
    
    # Optional result data
    data: Optional[List[Dict[str, Any]]] = Field(None, description="Operation result data")
    error_message: Optional[str] = Field(None, description="Error message if operation failed")
    
    # Metadata
    spreadsheet_id: Optional[str] = Field(None, description="Google Sheets spreadsheet ID")
    worksheet_name: Optional[str] = Field(None, description="Worksheet name")
    range_updated: Optional[str] = Field(None, description="Range that was updated")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class BackupResult(BaseModel):
    """Result model for backup operations."""
    
    success: bool = Field(..., description="Backup success status")
    backup_path: str = Field(..., description="Path to backup file")
    backup_format: str = Field(..., description="Backup file format (csv, json)")
    rows_exported: int = Field(default=0, ge=0, description="Number of rows exported")
    file_size_bytes: int = Field(default=0, ge=0, description="Backup file size in bytes")
    
    # Timestamps
    backup_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Backup creation timestamp")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Backup operation duration")
    
    # Optional error information
    error_message: Optional[str] = Field(None, description="Error message if backup failed")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True


class BatchDuplicateCheckResponse(BaseModel):
    """Response model for batch duplicate checking."""
    
    batch_id: str = Field(..., description="Batch identifier")
    success: bool = Field(..., description="Batch success status")
    
    # Results
    decisions: List[DuplicateDecision] = Field(default_factory=list, description="Duplicate decisions")
    failed_checks: List[Dict[str, str]] = Field(default_factory=list, description="Failed check details")
    
    # Statistics
    total_companies: int = Field(default=0, ge=0, description="Total companies processed")
    duplicates_found: int = Field(default=0, ge=0, description="Number of duplicates found")
    unique_companies: int = Field(default=0, ge=0, description="Number of unique companies")
    failed_companies: int = Field(default=0, ge=0, description="Number of failed checks")
    
    # Performance metadata
    total_duration_seconds: float = Field(default=0.0, ge=0.0, description="Total batch duration")
    average_check_duration_ms: float = Field(default=0.0, ge=0.0, description="Average check duration")
    
    @validator('total_companies')
    def validate_total_companies(cls, v: int, values: Dict[str, Any]) -> int:
        """Validate total companies matches results."""
        decisions = values.get('decisions', [])
        failed_checks = values.get('failed_checks', [])
        if isinstance(decisions, list) and isinstance(failed_checks, list):
            return len(decisions) + len(failed_checks)
        return v
    
    @validator('duplicates_found')
    def calculate_duplicates_found(cls, v: int, values: Dict[str, Any]) -> int:
        """Calculate duplicates found from decisions."""
        decisions = values.get('decisions', [])
        if isinstance(decisions, list):
            return sum(1 for decision in decisions if decision.is_duplicate)
        return v
    
    @validator('unique_companies')
    def calculate_unique_companies(cls, v: int, values: Dict[str, Any]) -> int:
        """Calculate unique companies from decisions."""
        decisions = values.get('decisions', [])
        if isinstance(decisions, list):
            return sum(1 for decision in decisions if not decision.is_duplicate)
        return v
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class LeadStatus(str, Enum):
    """Lead processing status enumeration."""
    NEW = "new"
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    CONVERTED = "converted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    ERROR = "error"


class LeadData(BaseModel):
    """Lead data model for Google Sheets storage.
    
    Represents a single lead with all required fields for the Tatvix AI
    Client Discovery system, including validation and schema enforcement.
    """
    
    # Core identification
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique lead identifier")
    company: str = Field(..., min_length=2, max_length=100, description="Company name")
    website: HttpUrl = Field(..., description="Company website URL")
    email: Optional[str] = Field(None, max_length=254, description="Primary contact email")
    
    # Geographic and industry information
    country: str = Field(..., min_length=2, max_length=3, description="ISO country code")
    industry: str = Field(..., min_length=2, max_length=100, description="Business industry category")
    
    # Scoring and status
    score: int = Field(..., ge=1, le=10, description="Lead quality score (1-10)")
    status: LeadStatus = Field(default=LeadStatus.NEW, description="Current processing status")
    source: str = Field(..., min_length=1, max_length=50, description="Discovery source attribution")
    
    # Personalized outreach content
    personalized_email: Optional[str] = Field(None, description="AI-generated personalized email content")
    email_subject: Optional[str] = Field(None, max_length=200, description="Personalized email subject line")
    
    # Timestamps
    created: datetime = Field(default_factory=datetime.utcnow, description="Lead discovery timestamp")
    updated: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    
    @validator('email')
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate email format if provided."""
        if v is None:
            return v
        
        # Basic email validation
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")
        
        return v.lower().strip()
    
    @validator('country')
    def validate_country_code(cls, v: str) -> str:
        """Validate country code format."""
        v = v.upper().strip()
        if len(v) not in [2, 3]:
            raise ValueError("Country code must be 2 or 3 characters (ISO format)")
        return v
    
    @validator('company')
    def validate_company_name(cls, v: str) -> str:
        """Validate and clean company name."""
        v = v.strip()
        if not v:
            raise ValueError("Company name cannot be empty")
        
        # Remove excessive whitespace
        v = ' '.join(v.split())
        return v
    
    @validator('industry')
    def validate_industry_category(cls, v: str) -> str:
        """Validate industry category."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Industry category cannot be empty")
        return v
    
    @validator('source')
    def validate_source_attribution(cls, v: str) -> str:
        """Validate source attribution."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Source attribution cannot be empty")
        return v
    
    @validator('updated', pre=True, always=True)
    def set_updated_timestamp(cls, v: Any) -> datetime:
        """Ensure updated timestamp is always current."""
        return datetime.utcnow()
    
    def to_sheets_row(self) -> List[str]:
        """Convert lead data to Google Sheets row format matching user's sheet structure.
        
        Returns:
            List of string values for spreadsheet insertion in format:
            [Lead Found Date, Company Name, Website, Industry, Location, Subject, Email, Email Address]
        """
        from datetime import datetime
        
        # Format date as DD/MM/YYYY to match user's format
        lead_found_date = datetime.now().strftime('%d/%m/%Y')
        
        # Create location string (City, Country format)
        location = f"Global, {self.country}" if self.country else "Global"
        
        # Use personalized subject or create default
        subject = self.email_subject or f"Engineering partnership opportunities with {self.company}"
        
        # Use personalized email content or create default
        email_content = self.personalized_email or f"""Hello,

I recently came across {self.company} and your work in the {self.industry} space. Your approach to building innovative solutions is impressive.

At Tatvix Technologies we work with companies building connected hardware systems where embedded firmware, device connectivity, and backend infrastructure need to operate together reliably. Our team often supports engineering groups working on IoT telemetry platforms, device monitoring dashboards, and backend systems for distributed hardware infrastructure.

If your team ever needs additional engineering bandwidth around device connectivity, embedded systems, or infrastructure monitoring platforms, we would be glad to explore whether we could support your development efforts."""
        
        # Generate email address from domain
        email_address = self.email or generate_default_email(self.website)
        
        return [
            lead_found_date,        # Lead Found Date
            self.company,           # Company Name  
            str(self.website),      # Website
            self.industry,          # Industry
            location,               # Location (City, Country)
            subject,                # Subject
            email_content,          # Email (personalized content)
            email_address           # Email Address
        ]
    
    @classmethod
    def from_sheets_row(cls, row: List[str]) -> 'LeadData':
        """Create LeadData instance from Google Sheets row.
        
        Args:
            row: List of string values from spreadsheet.
            
        Returns:
            LeadData instance.
            
        Raises:
            ValueError: If row data is invalid or incomplete.
        """
        if len(row) < 11:
            raise ValueError(f"Insufficient row data: expected 11 columns, got {len(row)}")
        
        try:
            return cls(
                id=row[0] if row[0] else str(uuid.uuid4()),
                company=row[1],
                website=row[2],
                email=row[3] if row[3] else None,
                country=row[4],
                industry=row[5],
                score=int(row[6]),
                status=LeadStatus(row[7]) if row[7] else LeadStatus.NEW,
                source=row[8],
                created=datetime.fromisoformat(row[9]) if row[9] else datetime.utcnow(),
                updated=datetime.fromisoformat(row[10]) if row[10] else datetime.utcnow()
            )
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid row data format: {e}")
    
    @classmethod
    def get_headers(cls) -> List[str]:
        """Get column headers for Google Sheets.
        
        Returns:
            List of column header names.
        """
        return [
            "ID",
            "Company", 
            "Website",
            "Email",
            "Country",
            "Industry",
            "Score",
            "Status",
            "Source",
            "Created",
            "Updated"
        ]
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            HttpUrl: str
        }
        validate_assignment = True
        use_enum_values = True


class SheetsOperationResult(BaseModel):
    """Result model for Google Sheets operations."""
    
    success: bool = Field(..., description="Operation success status")
    operation_type: str = Field(..., description="Type of operation performed")
    rows_affected: int = Field(default=0, ge=0, description="Number of rows affected")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Operation duration in milliseconds")
    
    # Optional result data
    data: Optional[List[Dict[str, Any]]] = Field(None, description="Operation result data")
    error_message: Optional[str] = Field(None, description="Error message if operation failed")
    
    # Metadata
    spreadsheet_id: Optional[str] = Field(None, description="Google Sheets spreadsheet ID")
    worksheet_name: Optional[str] = Field(None, description="Worksheet name")
    range_updated: Optional[str] = Field(None, description="Range that was updated")
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True


class BackupResult(BaseModel):
    """Result model for backup operations."""
    
    success: bool = Field(..., description="Backup success status")
    backup_path: str = Field(..., description="Path to backup file")
    backup_format: str = Field(..., description="Backup file format (csv, json)")
    rows_exported: int = Field(default=0, ge=0, description="Number of rows exported")
    file_size_bytes: int = Field(default=0, ge=0, description="Backup file size in bytes")
    
    # Timestamps
    backup_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Backup creation timestamp")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Backup operation duration")
    
    # Optional error information
    error_message: Optional[str] = Field(None, description="Error message if backup failed")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_assignment = True