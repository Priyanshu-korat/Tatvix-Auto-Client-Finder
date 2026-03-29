"""Multi-source lead discovery engine.

This module implements the main orchestration class for discovering leads
from multiple sources including GitHub, startup directories, patents, and job boards.
"""

import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
import logging

from .models import (
    Lead, LeadSource, LeadSourceType, LeadConfidence, UnifiedLead,
    DiscoveryBatch, DiscoveryResult, SearchStatus
)
from .github_adapter import GitHubAdapter
from .startup_adapters import (
    ProductHuntAdapter, CrunchbaseAdapter, F6SAdapter, 
    GustAdapter, AngelListAdapter
)
from .patent_adapter import USPTOAdapter, GooglePatentsAdapter
from .job_board_adapter import LinkedInJobsAdapter, IndeedAdapter, GlassdoorAdapter
from .url_utils import normalize_domain
from config.settings import Settings
from utils.exceptions import ConfigurationError, DiscoveryError
from utils.logger import get_logger


logger = get_logger(__name__)


class MultiSourceDiscovery:
    """Multi-source lead discovery orchestration engine.
    
    Coordinates lead discovery across multiple sources with deduplication,
    aggregation, and quality scoring.
    """
    
    def __init__(self, config: Settings) -> None:
        """Initialize multi-source discovery engine.
        
        Args:
            config: Application configuration settings.
        """
        self.config = config
        
        # Initialize source adapters
        self.adapters = self._initialize_adapters()
        
        # Discovery configuration
        self.max_concurrent_sources = config.get_int('discovery', 'max_concurrent_sources', fallback=4)
        self.default_timeout = config.get_int('discovery', 'timeout_seconds', fallback=7200)  # 2 hours
        self.duplicate_threshold = config.get_float('discovery', 'duplicate_threshold', fallback=0.9)
        
        # Quality thresholds
        self.min_confidence_threshold = config.get('discovery', 'min_confidence_level', fallback='low')
        self.min_relevance_score = config.get_float('discovery', 'min_relevance_score', fallback=0.3)
        
        # Default search configuration
        self.default_keywords = config.get_list('discovery', 'default_keywords', fallback=[
            'IoT', 'embedded systems', 'smart devices', 'industrial IoT',
            'connected devices', 'sensor networks', 'edge computing'
        ])
        
        self.default_categories = config.get_list('discovery', 'default_categories', fallback=[
            'hardware', 'iot', 'embedded', 'smart-home', 'industrial'
        ])
        
        self.default_job_keywords = config.get_list('discovery', 'default_job_keywords', fallback=[
            'embedded software engineer', 'firmware engineer', 'IoT developer',
            'hardware engineer', 'embedded systems engineer'
        ])
        
        # Performance tracking
        self.discovery_stats = {
            'total_runs': 0,
            'successful_runs': 0,
            'total_leads_discovered': 0,
            'total_unified_leads': 0,
            'average_execution_time': 0.0,
            'source_performance': defaultdict(dict)
        }
    
    def _initialize_adapters(self) -> Dict[LeadSourceType, Any]:
        """Initialize all source adapters.
        
        Returns:
            Dictionary mapping source types to adapter instances.
        """
        adapters = {}
        
        try:
            # GitHub adapter
            if self.config.get_bool('github', 'enabled', fallback=True):
                adapters[LeadSourceType.GITHUB] = GitHubAdapter(self.config)
            
            # Startup directory adapters
            if self.config.get_bool('product_hunt', 'enabled', fallback=True):
                adapters[LeadSourceType.PRODUCT_HUNT] = ProductHuntAdapter(self.config)
            
            if self.config.get_bool('crunchbase', 'enabled', fallback=True):
                adapters[LeadSourceType.CRUNCHBASE] = CrunchbaseAdapter(self.config)
            
            if self.config.get_bool('f6s', 'enabled', fallback=True):
                adapters[LeadSourceType.F6S] = F6SAdapter(self.config)
            
            if self.config.get_bool('gust', 'enabled', fallback=True):
                adapters[LeadSourceType.GUST] = GustAdapter(self.config)
            
            if self.config.get_bool('angellist', 'enabled', fallback=True):
                adapters[LeadSourceType.ANGELLIST] = AngelListAdapter(self.config)
            
            # Patent adapters
            if self.config.get_bool('uspto', 'enabled', fallback=True):
                adapters[LeadSourceType.USPTO_PATENTS] = USPTOAdapter(self.config)
            
            if self.config.get_bool('google_patents', 'enabled', fallback=True):
                adapters[LeadSourceType.GOOGLE_PATENTS] = GooglePatentsAdapter(self.config)
            
            # Job board adapters
            if self.config.get_bool('linkedin_jobs', 'enabled', fallback=True):
                adapters[LeadSourceType.LINKEDIN_JOBS] = LinkedInJobsAdapter(self.config)
            
            if self.config.get_bool('indeed', 'enabled', fallback=True):
                adapters[LeadSourceType.INDEED] = IndeedAdapter(self.config)
            
            if self.config.get_bool('glassdoor', 'enabled', fallback=True):
                adapters[LeadSourceType.GLASSDOOR] = GlassdoorAdapter(self.config)
            
            logger.info(f"Initialized {len(adapters)} source adapters: {list(adapters.keys())}")
            return adapters
            
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize source adapters: {e}")
    
    async def discover_from_github(self, keywords: List[str]) -> List[Lead]:
        """Discover leads from GitHub repositories and organizations.
        
        Args:
            keywords: Search keywords for GitHub discovery.
            
        Returns:
            List of leads discovered from GitHub.
            
        Raises:
            DiscoveryError: If GitHub discovery fails.
        """
        if LeadSourceType.GITHUB not in self.adapters:
            logger.warning("GitHub adapter not enabled or configured")
            return []
        
        try:
            adapter = self.adapters[LeadSourceType.GITHUB]
            leads = await adapter.discover_from_github(keywords)
            
            logger.info(f"GitHub discovery completed: {len(leads)} leads")
            return leads
            
        except Exception as e:
            logger.error(f"GitHub discovery failed: {e}")
            raise DiscoveryError(f"GitHub discovery failed: {e}")
    
    async def scrape_startup_directories(self, categories: List[str]) -> List[Lead]:
        """Scrape startup directories for leads.
        
        Args:
            categories: Search categories for startup directories.
            
        Returns:
            List of leads discovered from startup directories.
            
        Raises:
            DiscoveryError: If startup directory discovery fails.
        """
        startup_adapters = [
            LeadSourceType.PRODUCT_HUNT, LeadSourceType.CRUNCHBASE,
            LeadSourceType.F6S, LeadSourceType.GUST, LeadSourceType.ANGELLIST
        ]
        
        available_adapters = [
            source_type for source_type in startup_adapters 
            if source_type in self.adapters
        ]
        
        if not available_adapters:
            logger.warning("No startup directory adapters enabled")
            return []
        
        try:
            all_leads = []
            
            # Run startup directory discovery concurrently
            tasks = []
            for source_type in available_adapters:
                adapter = self.adapters[source_type]
                task = asyncio.create_task(
                    adapter.discover_leads(categories),
                    name=f"startup_{source_type.value}"
                )
                tasks.append(task)
            
            # Wait for all tasks with timeout
            timeout = self.config.get_int('startup_directories', 'timeout', fallback=1800)  # 30 min
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            
            # Process results
            for i, result in enumerate(results):
                source_type = available_adapters[i]
                if isinstance(result, Exception):
                    logger.error(f"Startup directory {source_type.value} failed: {result}")
                    continue
                
                if isinstance(result, list):
                    all_leads.extend(result)
                    logger.info(f"Startup directory {source_type.value}: {len(result)} leads")
            
            logger.info(f"Startup directories discovery completed: {len(all_leads)} total leads")
            return all_leads
            
        except asyncio.TimeoutError:
            logger.error("Startup directories discovery timed out")
            raise DiscoveryError("Startup directories discovery timed out")
        except Exception as e:
            logger.error(f"Startup directories discovery failed: {e}")
            raise DiscoveryError(f"Startup directories discovery failed: {e}")
    
    async def mine_patent_databases(self, search_terms: List[str]) -> List[Lead]:
        """Mine patent databases for leads.
        
        Args:
            search_terms: Patent search terms.
            
        Returns:
            List of leads discovered from patent databases.
            
        Raises:
            DiscoveryError: If patent mining fails.
        """
        patent_adapters = [LeadSourceType.USPTO_PATENTS, LeadSourceType.GOOGLE_PATENTS]
        
        available_adapters = [
            source_type for source_type in patent_adapters 
            if source_type in self.adapters
        ]
        
        if not available_adapters:
            logger.warning("No patent database adapters enabled")
            return []
        
        try:
            all_leads = []
            
            # Run patent mining concurrently
            tasks = []
            for source_type in available_adapters:
                adapter = self.adapters[source_type]
                task = asyncio.create_task(
                    adapter.mine_patents(search_terms),
                    name=f"patents_{source_type.value}"
                )
                tasks.append(task)
            
            # Wait for all tasks with timeout
            timeout = self.config.get_int('patents', 'timeout', fallback=1800)  # 30 min
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            
            # Process results
            for i, result in enumerate(results):
                source_type = available_adapters[i]
                if isinstance(result, Exception):
                    logger.error(f"Patent database {source_type.value} failed: {result}")
                    continue
                
                if isinstance(result, list):
                    all_leads.extend(result)
                    logger.info(f"Patent database {source_type.value}: {len(result)} leads")
            
            logger.info(f"Patent databases mining completed: {len(all_leads)} total leads")
            return all_leads
            
        except asyncio.TimeoutError:
            logger.error("Patent databases mining timed out")
            raise DiscoveryError("Patent databases mining timed out")
        except Exception as e:
            logger.error(f"Patent databases mining failed: {e}")
            raise DiscoveryError(f"Patent databases mining failed: {e}")
    
    async def analyze_job_postings(self, job_keywords: List[str]) -> List[Lead]:
        """Analyze job postings for leads.
        
        Args:
            job_keywords: Job search keywords.
            
        Returns:
            List of leads discovered from job postings.
            
        Raises:
            DiscoveryError: If job posting analysis fails.
        """
        job_adapters = [
            LeadSourceType.LINKEDIN_JOBS, LeadSourceType.INDEED, LeadSourceType.GLASSDOOR
        ]
        
        available_adapters = [
            source_type for source_type in job_adapters 
            if source_type in self.adapters
        ]
        
        if not available_adapters:
            logger.warning("No job board adapters enabled")
            return []
        
        try:
            all_leads = []
            
            # Run job analysis concurrently
            tasks = []
            for source_type in available_adapters:
                adapter = self.adapters[source_type]
                task = asyncio.create_task(
                    adapter.analyze_job_postings(job_keywords),
                    name=f"jobs_{source_type.value}"
                )
                tasks.append(task)
            
            # Wait for all tasks with timeout
            timeout = self.config.get_int('job_boards', 'timeout', fallback=1800)  # 30 min
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            
            # Process results
            for i, result in enumerate(results):
                source_type = available_adapters[i]
                if isinstance(result, Exception):
                    logger.error(f"Job board {source_type.value} failed: {result}")
                    continue
                
                if isinstance(result, list):
                    all_leads.extend(result)
                    logger.info(f"Job board {source_type.value}: {len(result)} leads")
            
            logger.info(f"Job postings analysis completed: {len(all_leads)} total leads")
            return all_leads
            
        except asyncio.TimeoutError:
            logger.error("Job postings analysis timed out")
            raise DiscoveryError("Job postings analysis timed out")
        except Exception as e:
            logger.error(f"Job postings analysis failed: {e}")
            raise DiscoveryError(f"Job postings analysis failed: {e}")
    
    def aggregate_leads(self, source_results: Dict[str, List[Lead]]) -> List[UnifiedLead]:
        """Aggregate leads from multiple sources into unified leads.
        
        Args:
            source_results: Dictionary mapping source names to lead lists.
            
        Returns:
            List of unified leads with deduplication and source attribution.
        """
        logger.info("Starting lead aggregation and deduplication")
        
        # Flatten all leads
        all_leads = []
        for source_name, leads in source_results.items():
            all_leads.extend(leads)
        
        if not all_leads:
            logger.warning("No leads to aggregate")
            return []
        
        # Group leads by normalized domain
        domain_groups = defaultdict(list)
        
        for lead in all_leads:
            # Create deduplication key
            if lead.domain:
                dedup_key = normalize_domain(lead.domain)
            else:
                # Fallback to company name normalization
                dedup_key = self._normalize_company_name(lead.company_name)
            
            domain_groups[dedup_key].append(lead)
        
        # Create unified leads
        unified_leads = []
        
        for dedup_key, grouped_leads in domain_groups.items():
            try:
                unified_lead = self._create_unified_lead(grouped_leads, dedup_key)
                if unified_lead:
                    unified_leads.append(unified_lead)
            except Exception as e:
                logger.error(f"Failed to create unified lead for key '{dedup_key}': {e}")
                continue
        
        # Sort by quality metrics
        unified_leads = self._sort_unified_leads(unified_leads)
        
        logger.info(f"Lead aggregation completed: {len(unified_leads)} unified leads from {len(all_leads)} raw leads")
        
        return unified_leads
    
    def _create_unified_lead(self, grouped_leads: List[Lead], dedup_key: str) -> Optional[UnifiedLead]:
        """Create unified lead from grouped leads.
        
        Args:
            grouped_leads: List of leads to unify.
            dedup_key: Deduplication key.
            
        Returns:
            Unified lead if valid, None otherwise.
        """
        if not grouped_leads:
            return None
        
        # Sort leads by confidence and relevance
        sorted_leads = sorted(
            grouped_leads,
            key=lambda x: (
                self._confidence_to_score(x.confidence_level),
                x.relevance_score or 0.0
            ),
            reverse=True
        )
        
        primary_lead = sorted_leads[0]
        
        # Aggregate information from all leads
        company_name = primary_lead.company_name
        primary_domain = primary_lead.domain or ''
        company_url = primary_lead.company_url
        
        # Merge descriptions (prefer longest non-empty)
        descriptions = [lead.description for lead in sorted_leads if lead.description]
        description = max(descriptions, key=len) if descriptions else None
        
        # Aggregate tags
        all_industry_tags = []
        all_technology_tags = []
        all_emails = []
        all_phones = []
        all_social_profiles = {}
        
        for lead in sorted_leads:
            all_industry_tags.extend(lead.industry_tags)
            all_technology_tags.extend(lead.technology_tags)
            all_emails.extend(lead.contact_emails)
            all_phones.extend(lead.contact_phones)
            all_social_profiles.update(lead.social_profiles)
        
        # Remove duplicates and limit
        industry_tags = list(dict.fromkeys(all_industry_tags))[:20]
        technology_tags = list(dict.fromkeys(all_technology_tags))[:30]
        contact_emails = list(dict.fromkeys(all_emails))[:10]
        contact_phones = list(dict.fromkeys(all_phones))[:5]
        
        # Determine overall confidence
        confidence_scores = [self._confidence_to_score(lead.confidence_level) for lead in sorted_leads]
        avg_confidence_score = sum(confidence_scores) / len(confidence_scores)
        overall_confidence = self._score_to_confidence(avg_confidence_score)
        
        # Calculate average relevance score
        relevance_scores = [lead.relevance_score for lead in sorted_leads if lead.relevance_score is not None]
        average_relevance_score = sum(relevance_scores) / len(relevance_scores) if relevance_scores else None
        
        # Geographic information (prefer primary lead)
        country = primary_lead.country
        region = primary_lead.region
        city = primary_lead.city
        
        try:
            unified_lead = UnifiedLead(
                company_name=company_name,
                primary_domain=primary_domain,
                company_url=company_url,
                description=description,
                industry_tags=industry_tags,
                technology_tags=technology_tags,
                source_leads=sorted_leads,
                primary_source=primary_lead.source_type,
                source_count=len(sorted_leads),
                overall_confidence=overall_confidence,
                average_relevance_score=average_relevance_score,
                source_diversity_score=0.0,  # Will be calculated by validator
                contact_emails=contact_emails,
                contact_phones=contact_phones,
                social_profiles=all_social_profiles,
                country=country,
                region=region,
                city=city,
                deduplication_key=dedup_key
            )
            
            return unified_lead
            
        except Exception as e:
            logger.error(f"Failed to create UnifiedLead: {e}")
            return None
    
    def _normalize_company_name(self, company_name: str) -> str:
        """Normalize company name for deduplication.
        
        Args:
            company_name: Raw company name.
            
        Returns:
            Normalized company name.
        """
        if not company_name:
            return ''
        
        # Convert to lowercase and remove extra spaces
        normalized = company_name.lower().strip()
        
        # Remove common suffixes
        suffixes = [
            'inc', 'incorporated', 'corp', 'corporation', 'ltd', 'limited',
            'llc', 'co', 'company', 'gmbh', 'ag', 'sa', 'bv', 'oy', 'ab'
        ]
        
        for suffix in suffixes:
            if normalized.endswith(f' {suffix}'):
                normalized = normalized[:-len(suffix)-1].strip()
            elif normalized.endswith(f'.{suffix}'):
                normalized = normalized[:-len(suffix)-1].strip()
        
        return normalized
    
    def _confidence_to_score(self, confidence: LeadConfidence) -> float:
        """Convert confidence enum to numeric score.
        
        Args:
            confidence: Confidence level enum.
            
        Returns:
            Numeric confidence score.
        """
        mapping = {
            LeadConfidence.HIGH: 1.0,
            LeadConfidence.MEDIUM: 0.6,
            LeadConfidence.LOW: 0.3,
            LeadConfidence.UNKNOWN: 0.1
        }
        return mapping.get(confidence, 0.1)
    
    def _score_to_confidence(self, score: float) -> LeadConfidence:
        """Convert numeric score to confidence enum.
        
        Args:
            score: Numeric confidence score.
            
        Returns:
            Confidence level enum.
        """
        if score >= 0.8:
            return LeadConfidence.HIGH
        elif score >= 0.5:
            return LeadConfidence.MEDIUM
        elif score >= 0.2:
            return LeadConfidence.LOW
        else:
            return LeadConfidence.UNKNOWN
    
    def _sort_unified_leads(self, unified_leads: List[UnifiedLead]) -> List[UnifiedLead]:
        """Sort unified leads by quality metrics.
        
        Args:
            unified_leads: List of unified leads to sort.
            
        Returns:
            Sorted list of unified leads.
        """
        return sorted(
            unified_leads,
            key=lambda x: (
                self._confidence_to_score(x.overall_confidence),
                x.average_relevance_score or 0.0,
                x.source_diversity_score,
                x.source_count
            ),
            reverse=True
        )
    
    async def run_full_discovery(self, 
                               keywords: Optional[List[str]] = None,
                               categories: Optional[List[str]] = None,
                               job_keywords: Optional[List[str]] = None,
                               patent_terms: Optional[List[str]] = None) -> DiscoveryResult:
        """Run full multi-source discovery process.
        
        Args:
            keywords: GitHub search keywords (uses defaults if None).
            categories: Startup directory categories (uses defaults if None).
            job_keywords: Job search keywords (uses defaults if None).
            patent_terms: Patent search terms (uses keywords if None).
            
        Returns:
            Complete discovery result with unified leads and metrics.
        """
        # Use defaults if not provided
        keywords = keywords or self.default_keywords
        categories = categories or self.default_categories
        job_keywords = job_keywords or self.default_job_keywords
        patent_terms = patent_terms or keywords
        
        # Create discovery batch
        batch = DiscoveryBatch(
            batch_id=f"discovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            enabled_sources=list(self.adapters.keys()),
            search_keywords=keywords,
            search_categories=categories,
            started_at=datetime.now(),
            status=SearchStatus.RUNNING
        )
        
        logger.info(f"Starting full discovery batch: {batch.batch_id}")
        
        try:
            start_time = datetime.now()
            source_results = {}
            failed_sources = []
            
            # Run discovery methods concurrently with limited concurrency
            semaphore = asyncio.Semaphore(self.max_concurrent_sources)
            
            async def run_github():
                async with semaphore:
                    try:
                        leads = await self.discover_from_github(keywords)
                        source_results['github'] = leads
                        return len(leads)
                    except Exception as e:
                        logger.error(f"GitHub discovery failed: {e}")
                        failed_sources.append('github')
                        return 0
            
            async def run_startups():
                async with semaphore:
                    try:
                        leads = await self.scrape_startup_directories(categories)
                        source_results['startup_directories'] = leads
                        return len(leads)
                    except Exception as e:
                        logger.error(f"Startup directories discovery failed: {e}")
                        failed_sources.append('startup_directories')
                        return 0
            
            async def run_patents():
                async with semaphore:
                    try:
                        leads = await self.mine_patent_databases(patent_terms)
                        source_results['patents'] = leads
                        return len(leads)
                    except Exception as e:
                        logger.error(f"Patent mining failed: {e}")
                        failed_sources.append('patents')
                        return 0
            
            async def run_jobs():
                async with semaphore:
                    try:
                        leads = await self.analyze_job_postings(job_keywords)
                        source_results['job_boards'] = leads
                        return len(leads)
                    except Exception as e:
                        logger.error(f"Job analysis failed: {e}")
                        failed_sources.append('job_boards')
                        return 0
            
            # Execute all discovery methods
            tasks = [run_github(), run_startups(), run_patents(), run_jobs()]
            
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=self.default_timeout
                )
                
                total_raw_leads = sum(r for r in results if isinstance(r, int))
                
            except asyncio.TimeoutError:
                logger.error("Discovery batch timed out")
                batch.status = SearchStatus.TIMEOUT
                failed_sources.append('timeout')
            
            # Aggregate leads
            unified_leads = self.aggregate_leads(source_results)
            
            # Filter by quality thresholds
            filtered_leads = self._filter_leads_by_quality(unified_leads)
            
            # Calculate metrics
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            # Update batch status
            batch.completed_at = end_time
            batch.status = SearchStatus.COMPLETED if not failed_sources else SearchStatus.FAILED
            batch.total_leads_discovered = sum(len(leads) for leads in source_results.values())
            batch.unified_leads_created = len(filtered_leads)
            batch.duplicate_leads_filtered = batch.total_leads_discovered - len(unified_leads)
            batch.failed_sources = failed_sources
            
            # Calculate performance metrics
            leads_per_second = len(filtered_leads) / execution_time if execution_time > 0 else 0.0
            duplicate_rate = (batch.duplicate_leads_filtered / batch.total_leads_discovered 
                            if batch.total_leads_discovered > 0 else 0.0)
            
            # Calculate source success rates
            source_success_rates = {}
            for source_name in ['github', 'startup_directories', 'patents', 'job_boards']:
                if source_name in failed_sources:
                    source_success_rates[source_name] = 0.0
                else:
                    source_success_rates[source_name] = 1.0
            
            # Calculate average confidence and source diversity
            if filtered_leads:
                avg_confidence = sum(
                    self._confidence_to_score(lead.overall_confidence) 
                    for lead in filtered_leads
                ) / len(filtered_leads)
                
                avg_diversity = sum(lead.source_diversity_score for lead in filtered_leads) / len(filtered_leads)
            else:
                avg_confidence = 0.0
                avg_diversity = 0.0
            
            # Create discovery result
            result = DiscoveryResult(
                batch=batch,
                unified_leads=filtered_leads,
                source_results=source_results,
                execution_time_seconds=execution_time,
                leads_per_second=leads_per_second,
                source_success_rates=source_success_rates,
                duplicate_rate=duplicate_rate,
                average_confidence=avg_confidence,
                source_diversity=avg_diversity
            )
            
            # Update statistics
            self._update_discovery_stats(result)
            
            logger.info(f"Discovery batch completed: {len(filtered_leads)} unified leads in {execution_time:.1f}s")
            
            return result
            
        except Exception as e:
            batch.status = SearchStatus.FAILED
            batch.completed_at = datetime.now()
            logger.error(f"Discovery batch failed: {e}")
            raise DiscoveryError(f"Discovery batch failed: {e}")
    
    def _filter_leads_by_quality(self, unified_leads: List[UnifiedLead]) -> List[UnifiedLead]:
        """Filter unified leads by quality thresholds.
        
        Args:
            unified_leads: List of unified leads to filter.
            
        Returns:
            Filtered list of high-quality leads.
        """
        filtered_leads = []
        
        confidence_threshold = LeadConfidence(self.min_confidence_threshold)
        confidence_score_threshold = self._confidence_to_score(confidence_threshold)
        
        for lead in unified_leads:
            # Check confidence threshold
            if self._confidence_to_score(lead.overall_confidence) < confidence_score_threshold:
                continue
            
            # Check relevance score threshold
            if (lead.average_relevance_score is not None and 
                lead.average_relevance_score < self.min_relevance_score):
                continue
            
            # Require minimum company information
            if not lead.company_name or len(lead.company_name.strip()) < 2:
                continue
            
            filtered_leads.append(lead)
        
        logger.info(f"Quality filtering: {len(filtered_leads)} leads passed from {len(unified_leads)} total")
        
        return filtered_leads
    
    def _update_discovery_stats(self, result: DiscoveryResult) -> None:
        """Update discovery performance statistics.
        
        Args:
            result: Discovery result to update stats from.
        """
        self.discovery_stats['total_runs'] += 1
        
        if result.batch.status == SearchStatus.COMPLETED:
            self.discovery_stats['successful_runs'] += 1
        
        self.discovery_stats['total_leads_discovered'] += result.batch.total_leads_discovered
        self.discovery_stats['total_unified_leads'] += result.batch.unified_leads_created
        
        # Update average execution time
        total_time = (self.discovery_stats['average_execution_time'] * 
                     (self.discovery_stats['total_runs'] - 1) + 
                     result.execution_time_seconds)
        self.discovery_stats['average_execution_time'] = total_time / self.discovery_stats['total_runs']
        
        # Update source performance
        for source_name, success_rate in result.source_success_rates.items():
            if source_name not in self.discovery_stats['source_performance']:
                self.discovery_stats['source_performance'][source_name] = {
                    'total_runs': 0,
                    'successful_runs': 0,
                    'success_rate': 0.0
                }
            
            source_stats = self.discovery_stats['source_performance'][source_name]
            source_stats['total_runs'] += 1
            
            if success_rate > 0.0:
                source_stats['successful_runs'] += 1
            
            source_stats['success_rate'] = (source_stats['successful_runs'] / 
                                          source_stats['total_runs'])
    
    def get_discovery_stats(self) -> Dict[str, Any]:
        """Get discovery performance statistics.
        
        Returns:
            Dictionary with performance statistics.
        """
        return dict(self.discovery_stats)
    
    def get_enabled_sources(self) -> List[LeadSourceType]:
        """Get list of enabled source types.
        
        Returns:
            List of enabled source type enums.
        """
        return list(self.adapters.keys())