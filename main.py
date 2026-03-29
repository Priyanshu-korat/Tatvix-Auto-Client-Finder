"""Main orchestration system for Tatvix AI Client Discovery System.

This module implements the TatvixClientFinder class that coordinates all
discovery and analysis components, manages workflow execution, implements
monitoring, and ensures system reliability.
"""

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import argparse
import signal

from config.settings import Settings
from config.constants import (
    DEFAULT_LEAD_COUNTRY, DEFAULT_LEAD_INDUSTRY, DEFAULT_LEAD_SCORE,
    DEFAULT_LEAD_SOURCE, DEFAULT_EMAIL_SUBJECT_TEMPLATE, DEFAULT_EMAIL_PATTERNS,
    DEFAULT_SEARCH_KEYWORDS, MULTI_SOURCE_SEARCH_KEYWORDS, TATVIX_COMPANY_DESCRIPTION,
    TATVIX_CAPABILITIES
)
from utils.logger import get_logger
from utils.exceptions import (
    ConfigurationError, 
    ExternalServiceError, 
    ValidationError,
    SearchError,
    ScrapingError,
    APIError
)

# Import all components
from agents.search_agent import SearchAgent
from agents.multi_source_discovery import MultiSourceDiscovery
from agents.website_scraper import WebsiteScraper
from agents.proxy_manager import ProxyManager
from agents.ai_analyzer import AIAnalyzer
from agents.email_extractor import EmailExtractor
from database.duplicate_checker import DuplicateChecker
from database.sheets_manager import SheetsManager
from database.vector_store import VectorStore
from database.vector_factory import create_vector_store

# Import models
from agents.models import SearchQuery, TargetType, CompanyData, UnifiedLead, Lead, LeadSourceType, LeadConfidence
from database.models import LeadData, LeadStatus
from orchestration_models import (
    ExecutionResult, PipelineResult, HealthStatus, RecoveryAction, PerformanceReport,
    PipelineStage, ExecutionStatus, HealthLevel, RecoveryActionType, ComponentHealth,
    StageResult, PerformanceMetrics, PipelineConfiguration
)


logger = get_logger(__name__)


class TatvixClientFinder:
    """Main orchestration system for the Tatvix AI Client Discovery System.
    
    Coordinates all discovery and analysis components, manages workflow execution,
    implements monitoring, and ensures system reliability.
    """
    
    def __init__(self, config: Optional[Settings] = None):
        """Initialize the Tatvix Client Finder orchestration system.
        
        Args:
            config: Application configuration settings. If None, loads from environment.
        """
        self.config = config or Settings()
        self.logger = get_logger(__name__)
        
        # Pipeline state
        self._current_execution_id: Optional[str] = None
        self._pipeline_start_time: Optional[datetime] = None
        self._stage_results: List[StageResult] = []
        self._recovery_actions: List[RecoveryAction] = []
        
        # Component instances
        self._search_agent: Optional[SearchAgent] = None
        self._multi_source_discovery: Optional[MultiSourceDiscovery] = None
        self._website_scraper: Optional[WebsiteScraper] = None
        self._ai_analyzer: Optional[AIAnalyzer] = None
        self._email_extractor: Optional[EmailExtractor] = None
        self._duplicate_checker: Optional[DuplicateChecker] = None
        self._sheets_manager: Optional[SheetsManager] = None
        self._vector_store: Optional[VectorStore] = None
        
        # Graceful shutdown handling
        self._shutdown_requested = False
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        self.logger.info("TatvixClientFinder orchestration system initialized")
    
    def _handle_shutdown(self, signum: int, frame) -> None:
        """Handle graceful shutdown signals."""
        self.logger.info(f"Shutdown signal received: {signum}")
        self._shutdown_requested = True
    
    def _validate_environment(self) -> None:
        """Validate that all required environment variables and configurations are set.
        
        Raises:
            ConfigurationError: If required configuration is missing or invalid.
        """
        required_configs = [
            ('groq_api_key', 'Groq API key'),
            ('google_sheets_id', 'Google Sheets ID'),
            ('google_sheets_credentials_path', 'Google Sheets credentials path')
        ]
        
        missing_configs = []
        for config_key, config_name in required_configs:
            if not getattr(self.config, config_key, None):
                missing_configs.append(config_name)
        
        if missing_configs:
            raise ConfigurationError(
                f"Missing required configuration: {', '.join(missing_configs)}. "
                f"Please check your .env file and ensure all required values are set."
            )
    
    async def _initialize_components(self) -> None:
        """Initialize all pipeline components with dependency injection."""
        try:
            self.logger.info("Initializing pipeline components")
            
            # Validate environment before initialization
            self._validate_environment()
            
            # Initialize vector store first (dependency for duplicate checker)
            self._vector_store = create_vector_store(self.config)
            
            # Initialize core components
            self._search_agent = SearchAgent(self.config)
            self._multi_source_discovery = MultiSourceDiscovery(self.config)
            
            # Initialize proxy manager for web scraping
            proxy_manager = ProxyManager(self.config)
            self._website_scraper = WebsiteScraper(self.config, proxy_manager)
            
            self._ai_analyzer = AIAnalyzer(self.config)
            self._email_extractor = EmailExtractor(self.config)
            self._duplicate_checker = DuplicateChecker(self.config, self._vector_store)
            self._sheets_manager = SheetsManager(self.config)
            
            self.logger.info("All pipeline components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {e}")
            raise ConfigurationError(f"Component initialization failed: {e}")
    
    async def run_daily_discovery(self, pipeline_config: Optional[PipelineConfiguration] = None) -> ExecutionResult:
        """Run the complete daily discovery pipeline.
        
        Args:
            pipeline_config: Pipeline configuration. If None, uses default configuration.
            
        Returns:
            Complete execution result with pipeline results, health status, and performance report.
            
        Raises:
            ConfigurationError: If configuration is invalid or missing required settings.
            ValidationError: If pipeline configuration validation fails.
        """
        # Input validation
        if pipeline_config is not None and not isinstance(pipeline_config, PipelineConfiguration):
            raise ValidationError("pipeline_config must be a PipelineConfiguration instance")
        
        execution_start = datetime.utcnow()
        self._pipeline_start_time = execution_start
        
        # Use default configuration if none provided
        if pipeline_config is None:
            pipeline_config = PipelineConfiguration(
                # Enable all pipeline stages
                enable_search_discovery=True,
                enable_multi_source_discovery=True,
                enable_website_scraping=True,
                enable_email_discovery=True,
                enable_ai_analysis=True,
                enable_duplicate_detection=True,
                enable_vector_indexing=True,
                
                # Production settings
                max_leads_per_source=10,
                max_concurrent_operations=5,
                pipeline_timeout_minutes=60
            )
        
        try:
            self.logger.info("Starting daily discovery pipeline execution")
            
            # Initialize components
            await self._initialize_components()
            
            # Perform health check before starting
            health_status = await self.monitor_system_health()
            if health_status.overall_health == HealthLevel.CRITICAL:
                raise ConfigurationError("System health check failed - cannot proceed with pipeline execution")
            
            # Execute the discovery pipeline
            pipeline_result = await self.execute_discovery_pipeline(pipeline_config)
            
            # Generate performance report
            performance_report = await self.generate_performance_report(pipeline_result)
            
            # Create execution result
            execution_result = ExecutionResult(
                configuration_snapshot=pipeline_config.dict(),
                feature_flags={
                    "search_discovery": pipeline_config.enable_search_discovery,
                    "multi_source_discovery": pipeline_config.enable_multi_source_discovery,
                    "website_scraping": pipeline_config.enable_website_scraping,
                    "email_discovery": pipeline_config.enable_email_discovery,
                    "ai_analysis": pipeline_config.enable_ai_analysis,
                    "duplicate_detection": pipeline_config.enable_duplicate_detection,
                    "vector_indexing": pipeline_config.enable_vector_indexing
                },
                pipeline_result=pipeline_result,
                health_status=await self.monitor_system_health(),
                performance_report=performance_report,
                recovery_actions=self._recovery_actions,
                execution_summary=self._generate_execution_summary(pipeline_result, performance_report)
            )
            
            self.logger.info(f"Daily discovery pipeline completed successfully in {(datetime.utcnow() - execution_start).total_seconds():.2f} seconds")
            return execution_result
            
        except Exception as e:
            self.logger.error(f"Daily discovery pipeline failed: {e}")
            
            # Create failed execution result
            failed_pipeline_result = PipelineResult(
                status=ExecutionStatus.FAILED,
                started_at=execution_start,
                completed_at=datetime.utcnow(),
                stage_results=self._stage_results,
                total_errors=1,
                error_summary={"pipeline_failure": 1}
            )
            
            # Generate basic performance report even on failure
            performance_report = await self.generate_performance_report(failed_pipeline_result)
            
            execution_result = ExecutionResult(
                configuration_snapshot=pipeline_config.dict() if pipeline_config else {},
                pipeline_result=failed_pipeline_result,
                health_status=await self.monitor_system_health(),
                performance_report=performance_report,
                recovery_actions=self._recovery_actions,
                execution_summary=f"Pipeline execution failed: {str(e)}"
            )
            
            return execution_result
    
    async def execute_discovery_pipeline(self, config: PipelineConfiguration) -> PipelineResult:
        """Execute the ordered discovery pipeline with error isolation.
        
        Args:
            config: Pipeline configuration settings.
            
        Returns:
            Pipeline execution result with stage-by-stage results.
        """
        pipeline_start = datetime.utcnow()
        self._stage_results = []
        
        try:
            self.logger.info("Starting discovery pipeline execution")
            
            # Stage 1: Initialization and Health Checks
            if not self._shutdown_requested:
                await self._execute_stage(
                    PipelineStage.INITIALIZATION,
                    self._stage_initialization,
                    config
                )
            
            # Stage 2: Search and Discovery
            discovered_leads = []
            if config.enable_search_discovery and not self._shutdown_requested:
                search_results = await self._execute_stage(
                    PipelineStage.SEARCH_DISCOVERY,
                    self._stage_search_discovery,
                    config
                )
                if search_results:
                    discovered_leads.extend(search_results)
            
            # Stage 3: Multi-Source Discovery
            if config.enable_multi_source_discovery and not self._shutdown_requested:
                multi_source_results = await self._execute_stage(
                    PipelineStage.MULTI_SOURCE_DISCOVERY,
                    self._stage_multi_source_discovery,
                    config
                )
                if multi_source_results:
                    discovered_leads.extend(multi_source_results)
            
            # Stage 4: Website Scraping and Enrichment
            enriched_leads = []
            if config.enable_website_scraping and discovered_leads and not self._shutdown_requested:
                enriched_leads = await self._execute_stage(
                    PipelineStage.WEBSITE_SCRAPING,
                    self._stage_website_scraping,
                    discovered_leads, config
                )
            else:
                enriched_leads = discovered_leads
            
            # Stage 5: Email Discovery
            if config.enable_email_discovery and enriched_leads and not self._shutdown_requested:
                enriched_leads = await self._execute_stage(
                    PipelineStage.EMAIL_DISCOVERY,
                    self._stage_email_discovery,
                    enriched_leads, config
                )
            
            # Stage 6: AI Analysis and Scoring
            analyzed_leads = []
            if config.enable_ai_analysis and enriched_leads and not self._shutdown_requested:
                analyzed_leads = await self._execute_stage(
                    PipelineStage.AI_ANALYSIS,
                    self._stage_ai_analysis,
                    enriched_leads, config
                )
            else:
                # Convert UnifiedLead objects to LeadData objects with AI-generated emails
                analyzed_leads = await self._execute_stage(
                    PipelineStage.AI_ANALYSIS,  # Reuse the same stage enum
                    self._stage_direct_conversion,
                    discovered_leads, config
                )
            
            # Stage 7: Duplicate Detection
            unique_leads = []
            if config.enable_duplicate_detection and analyzed_leads and not self._shutdown_requested:
                unique_leads = await self._execute_stage(
                    PipelineStage.DUPLICATE_DETECTION,
                    self._stage_duplicate_detection,
                    analyzed_leads, config
                )
            else:
                unique_leads = analyzed_leads
            
            # Stage 8: Data Storage
            stored_leads = []
            if unique_leads and not self._shutdown_requested:
                stored_leads = await self._execute_stage(
                    PipelineStage.DATA_STORAGE,
                    self._stage_data_storage,
                    unique_leads, config
                )
            
            # Stage 9: Vector Indexing
            if config.enable_vector_indexing and stored_leads and not self._shutdown_requested:
                await self._execute_stage(
                    PipelineStage.VECTOR_INDEXING,
                    self._stage_vector_indexing,
                    stored_leads, config
                )
            
            # Stage 10: Validation and Reporting
            if not self._shutdown_requested:
                await self._execute_stage(
                    PipelineStage.VALIDATION,
                    self._stage_validation,
                    stored_leads, config
                )
            
            # Calculate final metrics
            total_discovered = len(discovered_leads)
            total_stored = len(stored_leads) if stored_leads else 0
            duplicates_filtered = len(analyzed_leads) - len(unique_leads) if analyzed_leads and unique_leads else 0
            
            # Calculate average lead score
            average_score = None
            high_quality_count = 0
            if stored_leads:
                scores = [lead.score for lead in stored_leads if hasattr(lead, 'score')]
                if scores:
                    average_score = sum(scores) / len(scores)
                    high_quality_count = sum(1 for score in scores if score >= 7)
            
            # Determine final status
            final_status = ExecutionStatus.COMPLETED
            if self._shutdown_requested:
                final_status = ExecutionStatus.CANCELLED
            elif any(stage.status == ExecutionStatus.FAILED for stage in self._stage_results):
                if config.continue_on_stage_failure:
                    final_status = ExecutionStatus.DEGRADED
                else:
                    final_status = ExecutionStatus.FAILED
            
            # Create pipeline result
            pipeline_result = PipelineResult(
                started_at=pipeline_start,
                completed_at=datetime.utcnow(),
                status=final_status,
                stage_results=self._stage_results,
                failed_stages=[stage.stage for stage in self._stage_results if stage.status == ExecutionStatus.FAILED],
                total_leads_discovered=total_discovered,
                leads_processed=len(analyzed_leads) if analyzed_leads else 0,
                leads_stored=total_stored,
                duplicates_filtered=duplicates_filtered,
                average_lead_score=average_score,
                high_quality_leads=high_quality_count,
                total_errors=sum(stage.items_failed for stage in self._stage_results)
            )
            
            self.logger.info(f"Discovery pipeline completed with status: {final_status}")
            return pipeline_result
            
        except Exception as e:
            self.logger.error(f"Discovery pipeline execution failed: {e}")
            
            # Create failed pipeline result
            failed_result = PipelineResult(
                started_at=pipeline_start,
                completed_at=datetime.utcnow(),
                status=ExecutionStatus.FAILED,
                stage_results=self._stage_results,
                total_errors=1,
                error_summary={"pipeline_exception": 1}
            )
            
            return failed_result
    
    async def _execute_stage(self, stage: PipelineStage, stage_func, *args) -> Any:
        """Execute a pipeline stage with error handling and recovery.
        
        Args:
            stage: Pipeline stage identifier.
            stage_func: Stage execution function.
            *args: Arguments to pass to stage function.
            
        Returns:
            Stage execution result.
        """
        stage_start = datetime.utcnow()
        
        try:
            self.logger.info(f"Executing pipeline stage: {stage.value}")
            
            # Execute stage with timeout
            result = await asyncio.wait_for(
                stage_func(*args),
                timeout=self.config.get_int('general', 'api_timeout', 300)
            )
            
            # Record successful stage result
            stage_result = StageResult(
                stage=stage,
                status=ExecutionStatus.COMPLETED,
                started_at=stage_start,
                completed_at=datetime.utcnow(),
                items_processed=len(result) if isinstance(result, list) else 1,
                items_successful=len(result) if isinstance(result, list) else 1,
                items_failed=0
            )
            
            self._stage_results.append(stage_result)
            self.logger.info(f"Stage {stage.value} completed successfully")
            
            return result
            
        except asyncio.TimeoutError:
            self.logger.error(f"Stage {stage.value} timed out")
            
            # Handle timeout with recovery
            recovery_action = await self.handle_pipeline_errors(
                TimeoutError(f"Stage {stage.value} timed out"),
                stage
            )
            
            stage_result = StageResult(
                stage=stage,
                status=ExecutionStatus.TIMEOUT,
                started_at=stage_start,
                completed_at=datetime.utcnow(),
                error_message=f"Stage timed out after {self.config.get_int('general', 'api_timeout', 300)} seconds"
            )
            
            self._stage_results.append(stage_result)
            
            if recovery_action.action_type == RecoveryActionType.ABORT_RUN:
                raise
            
            return None
            
        except Exception as e:
            self.logger.error(f"Stage {stage.value} failed: {e}")
            
            # Handle error with recovery
            recovery_action = await self.handle_pipeline_errors(e, stage)
            
            stage_result = StageResult(
                stage=stage,
                status=ExecutionStatus.FAILED,
                started_at=stage_start,
                completed_at=datetime.utcnow(),
                error_message=str(e),
                error_details={"exception_type": type(e).__name__, "traceback": traceback.format_exc()}
            )
            
            self._stage_results.append(stage_result)
            
            if recovery_action.action_type == RecoveryActionType.ABORT_RUN:
                raise
            
            return None
    
    async def _stage_initialization(self, config: PipelineConfiguration) -> bool:
        """Initialize pipeline and perform health checks."""
        self.logger.info("Initializing pipeline")
        
        # Initialize components if not already done
        if self._search_agent is None:
            await self._initialize_components()
        
        # Validate configuration
        self.config.validate_required_credentials()
        
        # Check system health
        health_status = await self.monitor_system_health()
        if health_status.overall_health == HealthLevel.CRITICAL:
            raise ConfigurationError("System health check failed during initialization")
        
        return True
    
    async def _stage_search_discovery(self, config: PipelineConfiguration) -> List[UnifiedLead]:
        """Execute web search discovery."""
        self.logger.info("Starting search discovery")
        
        # Generate search queries from configuration
        search_queries = []
        target_types = [TargetType.IOT_SOFTWARE, TargetType.EMBEDDED_SYSTEMS, TargetType.HARDWARE_STARTUP]
        
        for i, query_text in enumerate(DEFAULT_SEARCH_KEYWORDS):
            target_type = target_types[i % len(target_types)]
            search_queries.append(SearchQuery(
                query=query_text,
                target_type=target_type,
                max_results=config.max_leads_per_source
            ))
        
        discovered_leads = []
        for query in search_queries:
            if self._shutdown_requested:
                break
                
            try:
                search_responses = await self._search_agent.search_companies([query])
                
                # Convert search results to unified leads
                for search_response in search_responses:
                    for result in search_response.results:
                        # Extract proper company name from title and domain
                        company_name = self._extract_company_name(result.title, result.domain)
                        
                        # Skip if we can't extract a proper company name
                        if not company_name or len(company_name) < 3:
                            continue
                        
                        # Create a source Lead object first
                        source_lead = Lead(
                            company_name=company_name,
                            domain=result.domain,
                            company_url=result.url,
                            description=result.snippet,
                            source_type=LeadSourceType.WEB_SEARCH,  # Use appropriate enum value
                            confidence_level=LeadConfidence.MEDIUM
                        )
                        
                        # Create UnifiedLead with proper validation
                        lead = UnifiedLead(
                            company_name=company_name,
                            primary_domain=result.domain,
                            company_url=result.url,
                            description=result.snippet,
                            source_leads=[source_lead],  # Must have at least 1 item
                            primary_source=LeadSourceType.WEB_SEARCH,  # Use valid enum
                            source_count=1,
                            overall_confidence=LeadConfidence.MEDIUM,  # Use enum
                            source_diversity_score=0.5,  # Required field
                            deduplication_key=result.domain  # Required field
                        )
                        discovered_leads.append(lead)
                    
            except Exception as e:
                self.logger.warning(f"Search query failed: {query.query} - {e}")
                continue
        
        self.logger.info(f"Search discovery found {len(discovered_leads)} leads")
        return discovered_leads
    
    def _extract_company_name(self, title: str, domain: str) -> str:
        """Extract proper company name from search result title and domain."""
        
        # Clean the title
        title = title.strip()
        
        # Remove common suffixes and prefixes
        title = title.split(' - ')[0].split(' | ')[0].split(' : ')[0]
        
        # Extract company name from domain or title
        
        # Extract company name from domain if it looks like a company
        if '.' in domain:
            domain_parts = domain.lower().replace('www.', '').split('.')
            if len(domain_parts) >= 2:
                potential_name = domain_parts[0]
                
                # Capitalize properly
                if potential_name and len(potential_name) > 2:
                    return potential_name.capitalize()
        
        # If title looks like a company name (not an article title)
        if not any(word in title.lower() for word in ['top', 'best', 'list', 'companies', 'startups', '10', 'guide']):
            # Clean up the title to extract company name
            cleaned_title = title.replace('Inc.', '').replace('LLC', '').replace('Ltd.', '').strip()
            if len(cleaned_title) > 2 and len(cleaned_title) < 50:
                return cleaned_title
        
        # Fallback to domain-based name
        return domain.replace('www.', '').split('.')[0].capitalize()
    
    async def _stage_direct_conversion(self, leads: List[UnifiedLead], config: PipelineConfiguration) -> List[LeadData]:
        """Convert UnifiedLead objects directly to LeadData objects with AI-generated emails."""
        self.logger.info(f"Starting direct conversion for {len(leads)} leads")
        
        converted_leads = []
        semaphore = asyncio.Semaphore(config.max_concurrent_operations)
        
        async def process_lead(lead: UnifiedLead) -> Optional[LeadData]:
            async with semaphore:
                try:
                    # Validate lead data
                    if not lead.company_name or not lead.company_url:
                        self.logger.warning(f"Skipping lead with missing required data: {lead}")
                        return None
                    # Generate personalized email using AI
                    personalized_email = await self._generate_personalized_email(
                        lead.company_name,
                        str(lead.company_url),
                        lead.description or f"Company in {DEFAULT_LEAD_INDUSTRY} space",
                        DEFAULT_LEAD_INDUSTRY
                    )
                    
                    # Create email address from domain using configured patterns
                    domain = str(lead.company_url).replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
                    email_address = DEFAULT_EMAIL_PATTERNS[0].format(domain=domain)  # Use first pattern as default
                    
                    # Convert to LeadData
                    lead_data = LeadData(
                        company=lead.company_name,
                        website=lead.company_url,
                        email=email_address,
                        country=DEFAULT_LEAD_COUNTRY,
                        industry=DEFAULT_LEAD_INDUSTRY,
                        score=DEFAULT_LEAD_SCORE,
                        source=DEFAULT_LEAD_SOURCE,
                        status=LeadStatus.ANALYZED,
                        personalized_email=personalized_email,
                        email_subject=DEFAULT_EMAIL_SUBJECT_TEMPLATE.format(company_name=lead.company_name)
                    )
                    
                    return lead_data
                    
                except Exception as e:
                    self.logger.warning(f"Failed to convert lead {lead.company_name}: {e}")
                    return None
        
        # Process all leads concurrently
        tasks = [process_lead(lead) for lead in leads]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None results and exceptions
        for result in results:
            if isinstance(result, LeadData):
                converted_leads.append(result)
        
        self.logger.info(f"Direct conversion completed for {len(converted_leads)} leads")
        return converted_leads
    
    async def _stage_multi_source_discovery(self, config: PipelineConfiguration) -> List[UnifiedLead]:
        """Execute multi-source discovery."""
        self.logger.info("Starting multi-source discovery")
        
        # Configure discovery batch
        from agents.models import DiscoveryBatch, LeadSourceType
        
        batch = DiscoveryBatch(
            batch_id=f"daily_discovery_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            enabled_sources=[
                LeadSourceType.GITHUB,
                LeadSourceType.PRODUCT_HUNT,
                LeadSourceType.CRUNCHBASE
            ],
            search_keywords=MULTI_SOURCE_SEARCH_KEYWORDS[:3],  # Use first 3 keywords
            max_leads_per_source=config.max_leads_per_source,
            concurrent_sources=config.max_concurrent_operations
        )
        
        # Execute discovery
        discovery_result = await self._multi_source_discovery.run_full_discovery(
            keywords=MULTI_SOURCE_SEARCH_KEYWORDS
        )
        
        self.logger.info(f"Multi-source discovery found {len(discovery_result.unified_leads)} leads")
        return discovery_result.unified_leads
    
    async def _stage_website_scraping(self, leads: List[UnifiedLead], config: PipelineConfiguration) -> List[Tuple[UnifiedLead, CompanyData]]:
        """Execute website scraping and enrichment."""
        self.logger.info(f"Starting website scraping for {len(leads)} leads")
        
        enriched_leads = []
        semaphore = asyncio.Semaphore(config.max_concurrent_operations)
        
        async def scrape_lead(lead: UnifiedLead) -> Optional[Tuple[UnifiedLead, CompanyData]]:
            async with semaphore:
                try:
                    company_data = await self._website_scraper.scrape_company_data(str(lead.company_url))
                    return (lead, company_data)
                except Exception as e:
                    self.logger.warning(f"Failed to scrape {lead.company_url}: {e}")
                    return None
        
        # Execute scraping with concurrency control
        tasks = [scrape_lead(lead) for lead in leads]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect successful results
        for result in results:
            if result and not isinstance(result, Exception):
                enriched_leads.append(result)
        
        self.logger.info(f"Website scraping completed for {len(enriched_leads)} leads")
        return enriched_leads
    
    async def _stage_email_discovery(self, enriched_leads: List[Tuple[UnifiedLead, CompanyData]], config: PipelineConfiguration) -> List[Tuple[UnifiedLead, CompanyData]]:
        """Execute email discovery for enriched leads."""
        self.logger.info(f"Starting email discovery for {len(enriched_leads)} leads")
        
        # Email discovery is performed in-place on the company data
        for lead, company_data in enriched_leads:
            if self._shutdown_requested:
                break
                
            try:
                # Discover emails for the domain
                email_result = await self._email_extractor.discover_emails(str(lead.company_url))
                
                # Update company data with discovered emails
                if email_result.email_candidates:
                    verified_emails = [
                        candidate.email_address 
                        for candidate in email_result.email_candidates 
                        if candidate.verification_status.value in ['valid', 'risky']
                    ]
                    company_data.contact_emails.extend(verified_emails)
                    
            except Exception as e:
                self.logger.warning(f"Email discovery failed for {lead.company_url}: {e}")
                continue
        
        self.logger.info(f"Email discovery completed for {len(enriched_leads)} leads")
        return enriched_leads
    
    async def _stage_ai_analysis(self, enriched_leads: List[Tuple[UnifiedLead, CompanyData]], config: PipelineConfiguration) -> List[LeadData]:
        """Execute AI analysis and lead scoring."""
        self.logger.info(f"Starting AI analysis for {len(enriched_leads)} leads")
        
        analyzed_leads = []
        semaphore = asyncio.Semaphore(config.max_concurrent_operations)
        
        async def analyze_lead(lead_data: Tuple[UnifiedLead, CompanyData]) -> Optional[LeadData]:
            async with semaphore:
                lead, company_data = lead_data
                
                try:
                    # Perform AI analysis
                    from agents.models import AnalysisRequest
                    
                    analysis_request = AnalysisRequest(company_data=company_data)
                    analysis_response = await self._ai_analyzer.analyze_company(analysis_request)
                    
                    if analysis_response.success and analysis_response.analysis:
                        analysis = analysis_response.analysis
                        
                        # Generate personalized email using AI
                        personalized_email = await self._generate_personalized_email(
                            lead.company_name, 
                            str(lead.company_url),
                            lead.description or "",
                            analysis.industry_classification.primary_industry.value
                        )
                        
                        # Generate personalized subject
                        email_subject = DEFAULT_EMAIL_SUBJECT_TEMPLATE.format(company_name=lead.company_name)
                        
                        # Convert to LeadData
                        lead_data = LeadData(
                            company=lead.company_name,
                            website=lead.company_url,
                            email=company_data.contact_emails[0] if company_data.contact_emails else None,
                            country=DEFAULT_LEAD_COUNTRY,  # Could be enhanced with geo detection
                            industry=analysis.industry_classification.primary_industry.value,
                            score=min(10, max(1, int(analysis.relevance_score.weighted_percentage / 10))),
                            source=lead.primary_source.value if hasattr(lead.primary_source, 'value') else str(lead.primary_source),
                            status=LeadStatus.ANALYZED,
                            personalized_email=personalized_email,
                            email_subject=email_subject
                        )
                        
                        return lead_data
                        
                except Exception as e:
                    self.logger.warning(f"AI analysis failed for {lead.company_name}: {e}")
                    return None
        
        # Execute analysis with concurrency control
        tasks = [analyze_lead(lead_data) for lead_data in enriched_leads]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect successful results
        for result in results:
            if result and not isinstance(result, Exception) and result.score >= config.min_lead_score:
                analyzed_leads.append(result)
        
        self.logger.info(f"AI analysis completed for {len(analyzed_leads)} qualified leads")
        return analyzed_leads
    
    async def _generate_personalized_email(self, company_name: str, website: str, description: str, industry: str) -> str:
        """Generate personalized email for a company using AI.
        
        Args:
            company_name: Name of the company
            website: Company website URL
            description: Company description
            industry: Company industry
            
        Returns:
            Generated personalized email content
            
        Raises:
            ValidationError: If required parameters are missing or invalid
        """
        # Input validation
        if not company_name or not company_name.strip():
            raise ValidationError("company_name is required and cannot be empty")
        
        if not website or not website.strip():
            raise ValidationError("website is required and cannot be empty")
        
        if not industry or not industry.strip():
            raise ValidationError("industry is required and cannot be empty")
        
        # Format capabilities list
        capabilities_list = "\n".join([f"- {capability}" for capability in TATVIX_CAPABILITIES])
        
        email_prompt = f"""
Write a personalized outreach email for Tatvix Technologies to {company_name}.

COMPANY CONTEXT:
- Company: {company_name}
- Website: {website}
- Description: {description}
- Industry: {industry}

REQUIREMENTS:
- Start with "Hello," (no name)
- Mention specific work {company_name} does based on their description
- Show genuine interest in their technology/business
- Include: "{TATVIX_COMPANY_DESCRIPTION}"
- Mention relevant Tatvix capabilities for this company
- End with offering engineering support in relevant areas
- NO placeholder text like [company name] or [specific areas]
- NO instructions or notes in the email
- Write a complete, ready-to-send email

TATVIX CAPABILITIES (choose relevant ones):
{capabilities_list}

Write a professional, technically credible email that shows genuine interest in {company_name}'s work.
"""

        try:
            # Validate API key availability
            if not self.config.groq_api_key:
                raise ConfigurationError("Groq API key is not configured")
            
            from groq import AsyncGroq
            groq_client = AsyncGroq(api_key=self.config.groq_api_key)
            
            response = await groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert at writing personalized B2B outreach emails for technical companies. Write professional, technically credible emails that show genuine interest in the recipient's work."},
                    {"role": "user", "content": email_prompt}
                ],
                model="llama-3.1-8b-instant",
                temperature=0.7,
                max_tokens=600
            )
            
            email_content = response.choices[0].message.content.strip()
            
            # Clean up the email
            if email_content.startswith("EMAIL:"):
                email_content = email_content[6:].strip()
                
            return email_content
            
        except Exception as e:
            self.logger.warning(f"AI email generation failed for {company_name}: {e}")
            # Fallback email using configuration
            return f"""Hello,

I recently came across {company_name} and your work in the {industry} space. {description[:100] if description else 'Your approach to building innovative solutions is impressive.'}

{TATVIX_COMPANY_DESCRIPTION} Our team often supports engineering groups working on IoT telemetry platforms, device monitoring dashboards, and backend systems for distributed hardware infrastructure.

If your team ever needs additional engineering bandwidth around device connectivity, embedded systems, or infrastructure monitoring platforms, we would be glad to explore whether we could support your development efforts."""
    
    async def _get_existing_companies_from_sheet(self) -> set:
        """Get list of existing companies from Google Sheet to prevent duplicates."""
        
        try:
            # Use the sheets manager to get existing companies
            # Read from column B (Company Name) of the sheet
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
            
            credentials = Credentials.from_service_account_file(
                self.config.google_sheets_credentials_path,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            service = build('sheets', 'v4', credentials=credentials)
            
            # Read existing data from Company Name column (B:B)
            result = service.spreadsheets().values().get(
                spreadsheetId=self.config.google_sheets_id,
                range='B:B'  # Company Name column
            ).execute()
            
            values = result.get('values', [])
            existing_companies = set()
            
            for row in values[1:]:  # Skip header row
                if row and len(row) > 0:
                    company_name = row[0].strip().lower()
                    existing_companies.add(company_name)
            
            return existing_companies
            
        except Exception as e:
            self.logger.warning(f"Could not read existing companies from Google Sheet: {e}")
            return set()
    
    async def _stage_duplicate_detection(self, leads: List[LeadData], config: PipelineConfiguration) -> List[LeadData]:
        """Execute duplicate detection including check against existing Google Sheet."""
        self.logger.info(f"Starting duplicate detection for {len(leads)} leads")
        
        # First, get existing companies from Google Sheet
        existing_companies = await self._get_existing_companies_from_sheet()
        self.logger.info(f"Found {len(existing_companies)} existing companies in Google Sheet")
        
        unique_leads = []
        
        for lead in leads:
            if self._shutdown_requested:
                break
                
            try:
                # Check against existing Google Sheet companies first
                company_name_lower = lead.company.lower().strip()
                if company_name_lower in existing_companies:
                    self.logger.debug(f"Filtered duplicate from Google Sheet: {lead.company}")
                    continue
                
                # Check for duplicates using vector similarity
                from database.models import DuplicateCheckRequest
                
                check_request = DuplicateCheckRequest(
                    company_data={
                        "company_name": lead.company,
                        "domain": str(lead.website).replace("https://", "").replace("http://", "").split("/")[0],
                        "website": str(lead.website)
                    },
                    similarity_threshold=config.duplicate_similarity_threshold
                )
                
                check_response = await self._duplicate_checker.check_duplicate(check_request)
                
                if check_response.success and check_response.decision:
                    if not check_response.decision.is_duplicate:
                        unique_leads.append(lead)
                    else:
                        self.logger.debug(f"Filtered duplicate lead: {lead.company}")
                else:
                    # If duplicate check fails, include the lead to be safe
                    unique_leads.append(lead)
                    
            except Exception as e:
                self.logger.warning(f"Duplicate check failed for {lead.company}: {e}")
                # Include lead if duplicate check fails
                unique_leads.append(lead)
        
        self.logger.info(f"Duplicate detection completed: {len(unique_leads)} unique leads from {len(leads)} total")
        return unique_leads
    
    async def _stage_data_storage(self, leads: List[LeadData], config: PipelineConfiguration) -> List[LeadData]:
        """Execute data storage to Google Sheets."""
        self.logger.info(f"Starting data storage for {len(leads)} leads")
        
        try:
            # Store leads in Google Sheets
            operation_result = await self._sheets_manager.insert_leads(leads)
            
            if operation_result.success:
                self.logger.info(f"Successfully stored {operation_result.rows_affected} leads")
                return leads
            else:
                self.logger.error(f"Failed to store leads: {operation_result.error_message}")
                return []
                
        except Exception as e:
            self.logger.error(f"Data storage failed: {e}")
            return []
    
    async def _stage_vector_indexing(self, leads: List[LeadData], config: PipelineConfiguration) -> bool:
        """Execute vector indexing for stored leads."""
        self.logger.info(f"Starting vector indexing for {len(leads)} leads")
        
        try:
            # Add leads to vector store for future duplicate detection
            for lead in leads:
                if self._shutdown_requested:
                    break
                    
                try:
                    # Create embedding record
                    from database.vector_store import EmbeddingRecord
                    import numpy as np
                    
                    # Simple text for embedding (would be enhanced with actual embedding model)
                    text = f"{lead.company} {lead.industry}"
                    
                    # Mock embedding (in real implementation, use sentence transformer)
                    embedding = np.random.rand(384)  # Mock 384-dimensional embedding
                    
                    record = EmbeddingRecord(
                        company_id=lead.id,
                        domain=str(lead.website).replace("https://", "").replace("http://", "").split("/")[0],
                        embedding=embedding,
                        metadata={
                            "company_name": lead.company,
                            "industry": lead.industry,
                            "score": lead.score
                        },
                        created_at=datetime.utcnow()
                    )
                    
                    await self._vector_store.add_embedding(record)
                    
                except Exception as e:
                    self.logger.warning(f"Failed to index lead {lead.company}: {e}")
                    continue
            
            self.logger.info("Vector indexing completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Vector indexing failed: {e}")
            return False
    
    async def _stage_validation(self, leads: List[LeadData], config: PipelineConfiguration) -> bool:
        """Execute final validation and metrics collection."""
        self.logger.info("Starting final validation")
        
        try:
            # Validate stored data
            validation_result = await self._sheets_manager.validate_data_integrity()
            
            if not validation_result:
                self.logger.warning("Data integrity validation failed")
                return False
            
            # Log final metrics
            self.logger.info(f"Pipeline validation completed successfully")
            self.logger.info(f"Total leads processed: {len(leads)}")
            
            if leads:
                avg_score = sum(lead.score for lead in leads) / len(leads)
                high_quality = sum(1 for lead in leads if lead.score >= 7)
                self.logger.info(f"Average lead score: {avg_score:.2f}")
                self.logger.info(f"High quality leads (score >= 7): {high_quality}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Validation failed: {e}")
            return False
    
    async def monitor_system_health(self) -> HealthStatus:
        """Monitor system health and component status.
        
        Returns:
            System health status with component-level details.
        """
        self.logger.debug("Performing system health check")
        
        component_health = []
        
        try:
            # Check configuration
            config_health = ComponentHealth(
                component_name="Configuration",
                health_level=HealthLevel.HEALTHY,
                status_message="Configuration loaded successfully"
            )
            
            try:
                self.config.validate_required_credentials()
                config_health.status_message = "All required credentials available"
            except ConfigurationError as e:
                config_health.health_level = HealthLevel.CRITICAL
                config_health.status_message = f"Missing credentials: {e}"
            
            component_health.append(config_health)
            
            # Check Google Sheets connectivity
            sheets_health = ComponentHealth(
                component_name="Google Sheets",
                health_level=HealthLevel.UNKNOWN,
                status_message="Checking connectivity..."
            )
            
            try:
                if self._sheets_manager:
                    # Test connection
                    test_start = time.time()
                    await self._sheets_manager.test_connection()
                    response_time = (time.time() - test_start) * 1000
                    
                    sheets_health.health_level = HealthLevel.HEALTHY
                    sheets_health.status_message = "Google Sheets connection successful"
                    sheets_health.response_time_ms = response_time
                else:
                    sheets_health.health_level = HealthLevel.WARNING
                    sheets_health.status_message = "Google Sheets manager not initialized"
                    
            except Exception as e:
                sheets_health.health_level = HealthLevel.CRITICAL
                sheets_health.status_message = f"Google Sheets connection failed: {e}"
            
            component_health.append(sheets_health)
            
            # Check vector store
            vector_health = ComponentHealth(
                component_name="Vector Store",
                health_level=HealthLevel.UNKNOWN,
                status_message="Checking vector store..."
            )
            
            try:
                if self._vector_store:
                    # Test vector store
                    test_start = time.time()
                    await self._vector_store.health_check()
                    response_time = (time.time() - test_start) * 1000
                    
                    vector_health.health_level = HealthLevel.HEALTHY
                    vector_health.status_message = "Vector store operational"
                    vector_health.response_time_ms = response_time
                else:
                    vector_health.health_level = HealthLevel.WARNING
                    vector_health.status_message = "Vector store not initialized"
                    
            except Exception as e:
                vector_health.health_level = HealthLevel.WARNING
                vector_health.status_message = f"Vector store check failed: {e}"
            
            component_health.append(vector_health)
            
            # Check system resources
            system_resources = {}
            try:
                import psutil
                
                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=1)
                system_resources["cpu_usage_percent"] = cpu_percent
                
                # Memory usage
                memory = psutil.virtual_memory()
                system_resources["memory_usage_percent"] = memory.percent
                system_resources["memory_available_gb"] = memory.available / (1024**3)
                
                # Disk usage
                disk = psutil.disk_usage('/')
                system_resources["disk_usage_percent"] = (disk.used / disk.total) * 100
                system_resources["disk_free_gb"] = disk.free / (1024**3)
                
            except ImportError:
                system_resources["note"] = "psutil not available for system monitoring"
            
            # Calculate overall health
            health_levels = [comp.health_level for comp in component_health]
            
            if HealthLevel.CRITICAL in health_levels:
                overall_health = HealthLevel.CRITICAL
            elif HealthLevel.WARNING in health_levels:
                overall_health = HealthLevel.WARNING
            elif all(level == HealthLevel.HEALTHY for level in health_levels):
                overall_health = HealthLevel.HEALTHY
            else:
                overall_health = HealthLevel.UNKNOWN
            
            health_status = HealthStatus(
                overall_health=overall_health,
                component_health=component_health,
                healthy_components=sum(1 for comp in component_health if comp.health_level == HealthLevel.HEALTHY),
                warning_components=sum(1 for comp in component_health if comp.health_level == HealthLevel.WARNING),
                critical_components=sum(1 for comp in component_health if comp.health_level == HealthLevel.CRITICAL),
                system_resources=system_resources,
                configuration_valid=config_health.health_level != HealthLevel.CRITICAL
            )
            
            self.logger.debug(f"System health check completed: {overall_health.value}")
            return health_status
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            
            # Return critical health status
            return HealthStatus(
                overall_health=HealthLevel.CRITICAL,
                component_health=[
                    ComponentHealth(
                        component_name="Health Check System",
                        health_level=HealthLevel.CRITICAL,
                        status_message=f"Health check system failed: {e}"
                    )
                ],
                configuration_valid=False
            )
    
    def handle_pipeline_errors(self, error: Exception, stage: PipelineStage) -> RecoveryAction:
        """Handle pipeline errors and determine recovery actions.
        
        Args:
            error: Exception that occurred.
            stage: Pipeline stage where error occurred.
            
        Returns:
            Recovery action to take.
        """
        self.logger.error(f"Handling error in stage {stage.value}: {error}")
        
        # Determine error type and appropriate recovery action
        error_type = type(error).__name__
        
        # Default recovery action
        action_type = RecoveryActionType.CONTINUE
        recovery_reason = f"Continuing after {error_type} in {stage.value}"
        
        # Specific error handling logic
        if isinstance(error, (ConfigurationError, ValidationError)):
            action_type = RecoveryActionType.ABORT_RUN
            recovery_reason = f"Critical configuration error: {error}"
            
        elif isinstance(error, (TimeoutError, asyncio.TimeoutError)):
            action_type = RecoveryActionType.RETRY
            recovery_reason = f"Timeout in {stage.value}, retrying with backoff"
            
        elif isinstance(error, (ExternalServiceError, APIError)):
            action_type = RecoveryActionType.RETRY
            recovery_reason = f"External service error in {stage.value}, retrying"
            
        elif isinstance(error, (SearchError, ScrapingError)):
            action_type = RecoveryActionType.CONTINUE
            recovery_reason = f"Non-critical {error_type} in {stage.value}, continuing pipeline"
            
        else:
            # Unknown error - be conservative
            action_type = RecoveryActionType.SKIP
            recovery_reason = f"Unknown error {error_type} in {stage.value}, skipping stage"
        
        # Create recovery action
        recovery_action = RecoveryAction(
            action_type=action_type,
            stage=stage,
            error_type=error_type,
            recovery_reason=recovery_reason,
            max_retries=self.config.get_int('general', 'max_retries', 3)
        )
        
        # Record recovery action
        self._recovery_actions.append(recovery_action)
        
        self.logger.info(f"Recovery action for {stage.value}: {action_type.value} - {recovery_reason}")
        return recovery_action
    
    async def generate_performance_report(self, pipeline_result: PipelineResult) -> PerformanceReport:
        """Generate comprehensive performance report.
        
        Args:
            pipeline_result: Pipeline execution result.
            
        Returns:
            Detailed performance analysis report.
        """
        self.logger.debug("Generating performance report")
        
        try:
            # Calculate basic metrics
            total_time = pipeline_result.total_duration_seconds
            throughput = (pipeline_result.leads_stored / (total_time / 3600)) if total_time > 0 else 0
            
            # Stage performance analysis
            stage_performance = {}
            for stage_result in pipeline_result.stage_results:
                stage_performance[stage_result.stage.value] = {
                    "duration_seconds": stage_result.duration_seconds,
                    "items_processed": stage_result.items_processed,
                    "success_rate": (stage_result.items_successful / stage_result.items_processed) 
                                  if stage_result.items_processed > 0 else 0,
                    "throughput_per_minute": (stage_result.items_processed / (stage_result.duration_seconds / 60))
                                           if stage_result.duration_seconds > 0 else 0
                }
            
            # Resource utilization metrics
            resource_metrics = {}
            try:
                import psutil
                
                resource_metrics["cpu"] = PerformanceMetrics(
                    metric_name="CPU Usage",
                    metric_value=psutil.cpu_percent(),
                    metric_unit="percentage",
                    target_value=80.0,
                    threshold_warning=85.0,
                    threshold_critical=95.0
                )
                
                memory = psutil.virtual_memory()
                resource_metrics["memory"] = PerformanceMetrics(
                    metric_name="Memory Usage",
                    metric_value=memory.percent,
                    metric_unit="percentage",
                    target_value=70.0,
                    threshold_warning=85.0,
                    threshold_critical=95.0
                )
                
            except ImportError:
                pass
            
            # Quality metrics
            quality_metrics = {}
            
            if pipeline_result.leads_stored > 0:
                quality_metrics["lead_quality"] = PerformanceMetrics(
                    metric_name="Average Lead Score",
                    metric_value=pipeline_result.average_lead_score or 0,
                    metric_unit="score",
                    target_value=6.0,
                    threshold_warning=4.0,
                    threshold_critical=3.0
                )
                
                quality_metrics["high_quality_rate"] = PerformanceMetrics(
                    metric_name="High Quality Lead Rate",
                    metric_value=(pipeline_result.high_quality_leads / pipeline_result.leads_stored) * 100,
                    metric_unit="percentage",
                    target_value=30.0,
                    threshold_warning=20.0,
                    threshold_critical=10.0
                )
            
            # Error analysis
            error_analysis = {
                "total_errors": pipeline_result.total_errors,
                "error_rate": (pipeline_result.total_errors / pipeline_result.total_leads_discovered) * 100
                             if pipeline_result.total_leads_discovered > 0 else 0,
                "failed_stages": [stage.value for stage in pipeline_result.failed_stages],
                "recovery_actions_taken": len(self._recovery_actions)
            }
            
            # Performance recommendations
            recommendations = []
            
            if pipeline_result.success_rate < 0.95:
                recommendations.append("Investigate failed stages to improve pipeline reliability")
            
            if throughput < 50:  # Less than 50 leads per hour
                recommendations.append("Consider increasing concurrency limits to improve throughput")
            
            if pipeline_result.total_errors > pipeline_result.total_leads_discovered * 0.1:
                recommendations.append("High error rate detected - review error handling and external service reliability")
            
            if pipeline_result.average_lead_score and pipeline_result.average_lead_score < 5.0:
                recommendations.append("Low average lead quality - review AI analysis criteria and source quality")
            
            # Create performance report
            performance_report = PerformanceReport(
                execution_id=pipeline_result.execution_id,
                report_period_start=pipeline_result.started_at,
                report_period_end=pipeline_result.completed_at or datetime.utcnow(),
                total_execution_time=total_time,
                throughput_leads_per_hour=throughput,
                success_rate_percentage=pipeline_result.success_rate * 100,
                stage_performance=stage_performance,
                resource_utilization=resource_metrics,
                quality_metrics=quality_metrics,
                error_analysis=error_analysis,
                performance_recommendations=recommendations
            )
            
            self.logger.debug("Performance report generated successfully")
            return performance_report
            
        except Exception as e:
            self.logger.error(f"Failed to generate performance report: {e}")
            
            # Return minimal report on failure
            return PerformanceReport(
                execution_id=pipeline_result.execution_id,
                report_period_start=pipeline_result.started_at,
                report_period_end=pipeline_result.completed_at or datetime.utcnow(),
                total_execution_time=pipeline_result.total_duration_seconds,
                throughput_leads_per_hour=0.0,
                success_rate_percentage=0.0,
                error_analysis={"report_generation_error": str(e)},
                performance_recommendations=["Fix performance reporting system"]
            )
    
    def _generate_execution_summary(self, pipeline_result: PipelineResult, performance_report: PerformanceReport) -> str:
        """Generate human-readable execution summary.
        
        Args:
            pipeline_result: Pipeline execution result.
            performance_report: Performance analysis report.
            
        Returns:
            Human-readable execution summary.
        """
        status_emoji = {
            ExecutionStatus.COMPLETED: "[PASS]",
            ExecutionStatus.DEGRADED: "[WARN]",
            ExecutionStatus.FAILED: "[FAIL]",
            ExecutionStatus.CANCELLED: "🚫",
            ExecutionStatus.TIMEOUT: "⏰"
        }
        
        emoji = status_emoji.get(pipeline_result.status, "❓")
        
        summary_lines = [
            f"{emoji} **Tatvix AI Client Discovery - Execution Summary**",
            f"",
            f"**Status:** {pipeline_result.status.value.upper()}",
            f"**Duration:** {pipeline_result.total_duration_seconds:.2f} seconds",
            f"**Success Rate:** {pipeline_result.success_rate:.1%}",
            f"",
            f"**Lead Processing:**",
            f"  • Discovered: {pipeline_result.total_leads_discovered}",
            f"  • Processed: {pipeline_result.leads_processed}",
            f"  • Stored: {pipeline_result.leads_stored}",
            f"  • Duplicates Filtered: {pipeline_result.duplicates_filtered}",
            f"",
            f"**Quality Metrics:**"
        ]
        
        if pipeline_result.average_lead_score:
            summary_lines.extend([
                f"  • Average Score: {pipeline_result.average_lead_score:.1f}/10",
                f"  • High Quality Leads: {pipeline_result.high_quality_leads}"
            ])
        else:
            summary_lines.append("  • No quality metrics available")
        
        summary_lines.extend([
            f"",
            f"**Performance:**",
            f"  • Throughput: {performance_report.throughput_leads_per_hour:.1f} leads/hour",
            f"  • Stages Completed: {len([s for s in pipeline_result.stage_results if s.status == ExecutionStatus.COMPLETED])}/{len(pipeline_result.stage_results)}"
        ])
        
        if pipeline_result.total_errors > 0:
            summary_lines.extend([
                f"",
                f"**Errors:**",
                f"  • Total Errors: {pipeline_result.total_errors}",
                f"  • Failed Stages: {', '.join(stage.value for stage in pipeline_result.failed_stages) if pipeline_result.failed_stages else 'None'}"
            ])
        
        if performance_report.performance_recommendations:
            summary_lines.extend([
                f"",
                f"**Recommendations:**"
            ])
            for rec in performance_report.performance_recommendations[:3]:  # Top 3 recommendations
                summary_lines.append(f"  • {rec}")
        
        return "\n".join(summary_lines)


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Tatvix AI Client Discovery System")
    parser.add_argument("command", choices=["run", "health", "report"], help="Command to execute")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--output", help="Output file path for results")
    parser.add_argument("--format", choices=["json", "text"], default="text", help="Output format")
    
    args = parser.parse_args()
    
    try:
        # Initialize system
        config = Settings()
        finder = TatvixClientFinder(config)
        
        if args.command == "run":
            # Run daily discovery pipeline
            print("Starting Tatvix AI Client Discovery Pipeline...")
            
            execution_result = await finder.run_daily_discovery()
            
            # Output results
            if args.output:
                output_path = Path(args.output)
                if args.format == "json":
                    with open(output_path, 'w') as f:
                        json.dump(execution_result.dict(), f, indent=2, default=str)
                else:
                    with open(output_path, 'w') as f:
                        f.write(execution_result.execution_summary)
            else:
                print(execution_result.execution_summary)
            
            # Exit with appropriate code
            if execution_result.pipeline_result.status == ExecutionStatus.COMPLETED:
                sys.exit(0)
            elif execution_result.pipeline_result.status == ExecutionStatus.DEGRADED:
                sys.exit(1)
            else:
                sys.exit(2)
        
        elif args.command == "health":
            # Perform health check
            print("Performing System Health Check...")
            
            health_status = await finder.monitor_system_health()
            
            # Output health status
            health_summary = f"""
System Health Status: {health_status.overall_health.value.upper()}

Component Health:
"""
            for component in health_status.component_health:
                status_icon = {"healthy": "[OK]", "warning": "[WARN]", "critical": "[ERROR]", "unknown": "[?]"}
                icon = status_icon.get(component.health_level.value, "❓")
                health_summary += f"  {icon} {component.component_name}: {component.status_message}\n"
            
            if health_status.system_resources:
                health_summary += f"\nSystem Resources:\n"
                for key, value in health_status.system_resources.items():
                    health_summary += f"  • {key}: {value}\n"
            
            print(health_summary)
            
            # Exit with health-based code
            if health_status.overall_health == HealthLevel.HEALTHY:
                sys.exit(0)
            elif health_status.overall_health == HealthLevel.WARNING:
                sys.exit(1)
            else:
                sys.exit(2)
        
        elif args.command == "report":
            print("Generating Performance Report...")
            print("Note: Report generation requires a completed pipeline execution.")
            print("Run 'python main.py run' first to generate execution data.")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled by user")
        sys.exit(130)
    
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        logger.error(f"CLI execution failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())