"""Job board intelligence adapter for lead discovery.

This module implements job board analysis for discovering IoT and embedded
systems companies through hiring signals and job postings.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urlparse, urljoin, quote
import logging

import httpx
from pydantic import HttpUrl

from .models import Lead, LeadSourceType, LeadConfidence
from .rate_limiter import RateLimiter
from .search_agent import SearchAgent
from config.settings import Settings
from utils.exceptions import APIError, RateLimitError
from utils.validators import validate_url, validate_domain


logger = logging.getLogger(__name__)


class JobBoardAdapter:
    """Base class for job board adapters."""
    
    def __init__(self, config: Settings, source_type: LeadSourceType) -> None:
        """Initialize job board adapter.
        
        Args:
            config: Application configuration settings.
            source_type: Type of job board source.
        """
        self.config = config
        self.source_type = source_type
        self.timeout = config.get_int('job_boards', 'timeout', fallback=30)
        self.max_retries = config.get_int('job_boards', 'max_retries', fallback=3)
        
        # Initialize search agent for search-based discovery
        self.search_agent = SearchAgent(config)
        
        # IoT/Embedded job keywords
        self.iot_job_keywords = [
            'iot developer', 'iot engineer', 'embedded software engineer', 'firmware engineer',
            'embedded systems engineer', 'hardware engineer', 'electronics engineer',
            'microcontroller programmer', 'rtos developer', 'device driver developer',
            'sensor engineer', 'wireless engineer', 'bluetooth developer', 'wifi engineer',
            'edge computing engineer', 'industrial iot engineer', 'automotive embedded',
            'medical device engineer', 'wearable developer', 'smart home developer',
            'robotics engineer', 'drone engineer', 'automation engineer', 'plc programmer',
            'scada engineer', 'control systems engineer', 'signal processing engineer'
        ]
        
        # Technology stack keywords for job analysis
        self.tech_stack_keywords = {
            'embedded_c': ['embedded c', 'c programming', 'c/c++', 'arm cortex'],
            'microcontrollers': ['arduino', 'raspberry pi', 'esp32', 'stm32', 'pic', 'avr'],
            'rtos': ['freertos', 'rtos', 'real-time', 'zephyr', 'mbed', 'threadx'],
            'wireless': ['bluetooth', 'wifi', 'zigbee', 'lora', 'cellular', '5g', 'nfc'],
            'protocols': ['mqtt', 'coap', 'http', 'tcp/ip', 'can bus', 'i2c', 'spi'],
            'tools': ['keil', 'iar', 'gcc', 'jtag', 'oscilloscope', 'logic analyzer'],
            'platforms': ['linux', 'android', 'yocto', 'buildroot', 'debian']
        }
        
        # Company size indicators from job descriptions
        self.company_size_indicators = {
            'startup': ['startup', 'early stage', 'seed funded', 'series a', 'fast-growing'],
            'small': ['small team', '10-50 employees', 'growing company', 'scale-up'],
            'medium': ['established company', '50-200 employees', 'mid-size', 'expanding team'],
            'large': ['enterprise', 'fortune 500', 'multinational', 'global company', '1000+ employees']
        }
    
    async def analyze_job_postings(self, job_keywords: List[str]) -> List[Lead]:
        """Analyze job postings for company leads.
        
        Args:
            job_keywords: Job search keywords.
            
        Returns:
            List of discovered leads from job postings.
        """
        raise NotImplementedError("Subclasses must implement analyze_job_postings method")
    
    def _calculate_iot_relevance(self, job_text: str) -> float:
        """Calculate IoT/embedded systems relevance score for job posting.
        
        Args:
            job_text: Job posting text to analyze.
            
        Returns:
            Relevance score between 0.0 and 1.0.
        """
        if not job_text:
            return 0.0
        
        text_lower = job_text.lower()
        matches = sum(1 for keyword in self.iot_job_keywords if keyword in text_lower)
        
        # Calculate base score
        base_score = min(matches / len(self.iot_job_keywords), 1.0)
        
        # Boost for high-value keywords
        high_value_keywords = ['iot engineer', 'embedded software', 'firmware engineer', 'industrial iot']
        boost = sum(0.1 for keyword in high_value_keywords if keyword in text_lower)
        
        return min(base_score + boost, 1.0)
    
    def _extract_company_from_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract company information from job posting data.
        
        Args:
            job_data: Job posting data dictionary.
            
        Returns:
            Dictionary with extracted company information.
        """
        company_name = job_data.get('company', '').strip()
        job_title = job_data.get('title', '')
        job_description = job_data.get('description', '')
        company_url = job_data.get('company_url', '')
        
        # Normalize company URL
        normalized_url = None
        domain = None
        
        if company_url and validate_url(company_url):
            normalized_url = HttpUrl(company_url)
            domain = validate_domain(urlparse(company_url).netloc)
        
        # Extract technology tags from job description
        technology_tags = self._extract_tech_stack_from_job(job_description)
        
        # Extract industry tags
        industry_tags = self._extract_industry_from_job(job_description)
        
        # Estimate company size
        company_size = self._estimate_company_size(job_description)
        
        # Extract location information
        location = job_data.get('location', '')
        
        # Create consolidated description
        description = self._create_job_based_description(job_title, job_description, company_size)
        
        return {
            'company_name': company_name,
            'company_url': normalized_url,
            'domain': domain,
            'description': description,
            'industry_tags': industry_tags,
            'technology_tags': technology_tags,
            'contact_emails': [],  # Job postings typically don't contain direct emails
            'location': location,
            'company_size': company_size,
            'job_title': job_title
        }
    
    def _extract_tech_stack_from_job(self, job_description: str) -> List[str]:
        """Extract technology stack tags from job description.
        
        Args:
            job_description: Job description text.
            
        Returns:
            List of technology tags.
        """
        text_lower = job_description.lower()
        found_tags = []
        
        for tech_category, keywords in self.tech_stack_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                found_tags.append(tech_category)
        
        return found_tags
    
    def _extract_industry_from_job(self, job_description: str) -> List[str]:
        """Extract industry tags from job description.
        
        Args:
            job_description: Job description text.
            
        Returns:
            List of industry tags.
        """
        text_lower = job_description.lower()
        
        industry_keywords = {
            'automotive': ['automotive', 'vehicle', 'car', 'truck', 'transportation', 'tesla', 'ford'],
            'healthcare': ['medical device', 'healthcare', 'patient monitoring', 'diagnostic', 'fda'],
            'industrial': ['industrial automation', 'manufacturing', 'factory', 'process control', 'plc'],
            'consumer_electronics': ['consumer electronics', 'smart phone', 'wearable', 'fitness tracker'],
            'smart_home': ['smart home', 'home automation', 'smart building', 'hvac', 'lighting'],
            'agriculture': ['precision agriculture', 'smart farming', 'agricultural', 'greenhouse'],
            'energy': ['renewable energy', 'smart grid', 'solar', 'wind', 'battery management'],
            'aerospace': ['aerospace', 'satellite', 'drone', 'uav', 'avionics', 'space'],
            'telecommunications': ['telecom', '5g', 'cellular', 'network infrastructure', 'base station'],
            'security': ['security systems', 'surveillance', 'access control', 'biometric']
        }
        
        found_tags = []
        for industry, keywords in industry_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                found_tags.append(industry)
        
        return found_tags
    
    def _estimate_company_size(self, job_description: str) -> str:
        """Estimate company size from job description.
        
        Args:
            job_description: Job description text.
            
        Returns:
            Estimated company size category.
        """
        text_lower = job_description.lower()
        
        for size_category, indicators in self.company_size_indicators.items():
            if any(indicator in text_lower for indicator in indicators):
                return size_category
        
        return 'unknown'
    
    def _create_job_based_description(self, job_title: str, job_description: str, 
                                    company_size: str) -> str:
        """Create company description based on job posting information.
        
        Args:
            job_title: Job title.
            job_description: Job description.
            company_size: Estimated company size.
            
        Returns:
            Generated company description.
        """
        # Extract key phrases from job description
        key_phrases = []
        
        # Look for company description patterns
        company_patterns = [
            r'(?:we are|company is|organization is)\s+([^.]{20,100})',
            r'(?:about us|about the company|company overview)[:.]?\s*([^.]{20,200})',
            r'(?:join|work with)\s+([^.]{10,80})\s+(?:team|company|organization)'
        ]
        
        for pattern in company_patterns:
            matches = re.findall(pattern, job_description, re.IGNORECASE)
            key_phrases.extend(matches)
        
        # Create description
        if key_phrases:
            description = key_phrases[0].strip()
        else:
            # Fallback: create description from job title and company size
            description = f"Company hiring {job_title.lower()} positions"
            if company_size != 'unknown':
                description += f" ({company_size} company)"
        
        return description[:500]  # Limit description length
    
    def _determine_job_confidence(self, job_data: Dict[str, Any], 
                                company_info: Dict[str, Any], 
                                relevance_score: float) -> LeadConfidence:
        """Determine confidence level for a job-derived lead.
        
        Args:
            job_data: Job posting data.
            company_info: Extracted company information.
            relevance_score: IoT relevance score.
            
        Returns:
            Confidence level enumeration.
        """
        confidence_score = 0
        
        # Company website availability
        if company_info['company_url']:
            confidence_score += 2
        
        # Job posting recency
        posted_date = job_data.get('posted_date', '')
        if posted_date:
            try:
                # Assume recent postings are more reliable
                post_date = datetime.strptime(posted_date[:10], '%Y-%m-%d')
                days_old = (datetime.now() - post_date).days
                if days_old <= 30:
                    confidence_score += 2
                elif days_old <= 90:
                    confidence_score += 1
            except:
                pass
        
        # IoT relevance
        if relevance_score >= 0.7:
            confidence_score += 2
        elif relevance_score >= 0.4:
            confidence_score += 1
        
        # Job description quality (longer descriptions typically more detailed)
        description_length = len(job_data.get('description', ''))
        if description_length > 1000:
            confidence_score += 1
        
        # Company size estimation (known size = higher confidence)
        if company_info['company_size'] != 'unknown':
            confidence_score += 1
        
        # Map score to confidence level
        if confidence_score >= 6:
            return LeadConfidence.HIGH
        elif confidence_score >= 3:
            return LeadConfidence.MEDIUM
        else:
            return LeadConfidence.LOW


class LinkedInJobsAdapter(JobBoardAdapter):
    """LinkedIn Jobs adapter using search-based discovery."""
    
    def __init__(self, config: Settings) -> None:
        """Initialize LinkedIn Jobs adapter."""
        super().__init__(config, LeadSourceType.LINKEDIN_JOBS)
    
    async def analyze_job_postings(self, job_keywords: List[str]) -> List[Lead]:
        """Analyze LinkedIn job postings for company leads.
        
        LinkedIn doesn't provide public API access for job searches,
        so we use search-based discovery.
        
        Args:
            job_keywords: Job search keywords.
            
        Returns:
            List of discovered leads from LinkedIn job postings.
        """
        logger.info("Starting LinkedIn Jobs search-based analysis")
        
        all_leads = []
        processed_companies = set()
        
        for keyword in job_keywords:
            query = f"site:linkedin.com/jobs {keyword} IoT embedded firmware engineer"
            
            try:
                search_results = await self.search_agent.search(query, max_results=20)
                
                for result in search_results.results:
                    job_info = self._extract_job_from_search_result(result)
                    
                    if not job_info:
                        continue
                    
                    company_name = job_info.get('company', '')
                    if not company_name or company_name in processed_companies:
                        continue
                    
                    processed_companies.add(company_name)
                    
                    lead = self._create_lead_from_job(job_info)
                    if lead and lead.relevance_score and lead.relevance_score > 0.3:
                        all_leads.append(lead)
            
            except Exception as e:
                logger.error(f"LinkedIn Jobs search failed for keyword '{keyword}': {e}")
                continue
        
        logger.info(f"LinkedIn Jobs analysis completed: {len(all_leads)} leads")
        return all_leads
    
    def _extract_job_from_search_result(self, result) -> Optional[Dict[str, Any]]:
        """Extract job information from LinkedIn search result.
        
        Args:
            result: Search result object.
            
        Returns:
            Job information dictionary if valid, None otherwise.
        """
        try:
            title = result.title
            snippet = result.snippet or ''
            
            # Extract company name from title (usually "Job Title at Company Name")
            company_match = re.search(r'\bat\s+([^-\n]+)', title)
            company_name = company_match.group(1).strip() if company_match else ''
            
            # Extract job title (before "at Company")
            job_title_match = re.match(r'^([^-]+?)(?:\s+at\s+)', title)
            job_title = job_title_match.group(1).strip() if job_title_match else title
            
            # Look for location in snippet
            location_match = re.search(r'(?:Location|Based in|Remote|Hybrid):\s*([^-\n]+)', snippet)
            location = location_match.group(1).strip() if location_match else ''
            
            if not company_name or not job_title:
                return None
            
            return {
                'title': job_title,
                'company': company_name,
                'description': snippet,
                'location': location,
                'posted_date': '',  # Not available from search results
                'company_url': '',  # Not directly available
                'source_url': str(result.url)
            }
            
        except Exception as e:
            logger.error(f"Error extracting LinkedIn job from search result: {e}")
            return None
    
    def _create_lead_from_job(self, job_data: Dict[str, Any]) -> Optional[Lead]:
        """Create lead from LinkedIn job data.
        
        Args:
            job_data: Job posting data.
            
        Returns:
            Lead object if valid, None otherwise.
        """
        try:
            # Extract company information
            company_info = self._extract_company_from_job(job_data)
            
            if not company_info['company_name']:
                return None
            
            # Calculate relevance score
            job_text = f"{job_data.get('title', '')} {job_data.get('description', '')}"
            relevance_score = self._calculate_iot_relevance(job_text)
            
            # Determine confidence
            confidence = self._determine_job_confidence(job_data, company_info, relevance_score)
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=f"linkedin_job:{job_data.get('source_url', '')}",
                source_url=HttpUrl(job_data.get('source_url', '')),
                source_metadata={
                    'job_title': company_info['job_title'],
                    'location': company_info['location'],
                    'company_size': company_info['company_size'],
                    'search_based': True
                },
                confidence_level=confidence,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"LinkedIn Jobs analysis"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from LinkedIn job: {e}")
            return None


class IndeedAdapter(JobBoardAdapter):
    """Indeed job board adapter using search-based discovery."""
    
    def __init__(self, config: Settings) -> None:
        """Initialize Indeed adapter."""
        super().__init__(config, LeadSourceType.INDEED)
    
    async def analyze_job_postings(self, job_keywords: List[str]) -> List[Lead]:
        """Analyze Indeed job postings for company leads.
        
        Args:
            job_keywords: Job search keywords.
            
        Returns:
            List of discovered leads from Indeed job postings.
        """
        logger.info("Starting Indeed search-based job analysis")
        
        all_leads = []
        processed_companies = set()
        
        for keyword in job_keywords:
            query = f"site:indeed.com {keyword} IoT embedded firmware hardware engineer"
            
            try:
                search_results = await self.search_agent.search(query, max_results=20)
                
                for result in search_results.results:
                    job_info = self._extract_job_from_search_result(result)
                    
                    if not job_info:
                        continue
                    
                    company_name = job_info.get('company', '')
                    if not company_name or company_name in processed_companies:
                        continue
                    
                    processed_companies.add(company_name)
                    
                    lead = self._create_lead_from_job(job_info)
                    if lead and lead.relevance_score and lead.relevance_score > 0.3:
                        all_leads.append(lead)
            
            except Exception as e:
                logger.error(f"Indeed search failed for keyword '{keyword}': {e}")
                continue
        
        logger.info(f"Indeed analysis completed: {len(all_leads)} leads")
        return all_leads
    
    def _extract_job_from_search_result(self, result) -> Optional[Dict[str, Any]]:
        """Extract job information from Indeed search result.
        
        Args:
            result: Search result object.
            
        Returns:
            Job information dictionary if valid, None otherwise.
        """
        try:
            title = result.title
            snippet = result.snippet or ''
            
            # Extract job title and company from title
            # Indeed format is usually "Job Title - Company Name"
            title_parts = title.split(' - ')
            if len(title_parts) >= 2:
                job_title = title_parts[0].strip()
                company_name = title_parts[1].strip()
            else:
                job_title = title
                # Try to extract company from snippet
                company_match = re.search(r'(?:Company|Employer):\s*([^-\n]+)', snippet)
                company_name = company_match.group(1).strip() if company_match else ''
            
            # Extract location from snippet
            location_match = re.search(r'(?:Location|City):\s*([^-\n]+)', snippet)
            location = location_match.group(1).strip() if location_match else ''
            
            if not company_name or not job_title:
                return None
            
            return {
                'title': job_title,
                'company': company_name,
                'description': snippet,
                'location': location,
                'posted_date': '',  # Not available from search results
                'company_url': '',  # Not directly available
                'source_url': str(result.url)
            }
            
        except Exception as e:
            logger.error(f"Error extracting Indeed job from search result: {e}")
            return None
    
    def _create_lead_from_job(self, job_data: Dict[str, Any]) -> Optional[Lead]:
        """Create lead from Indeed job data.
        
        Args:
            job_data: Job posting data.
            
        Returns:
            Lead object if valid, None otherwise.
        """
        try:
            # Extract company information
            company_info = self._extract_company_from_job(job_data)
            
            if not company_info['company_name']:
                return None
            
            # Calculate relevance score
            job_text = f"{job_data.get('title', '')} {job_data.get('description', '')}"
            relevance_score = self._calculate_iot_relevance(job_text)
            
            # Determine confidence
            confidence = self._determine_job_confidence(job_data, company_info, relevance_score)
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=f"indeed_job:{job_data.get('source_url', '')}",
                source_url=HttpUrl(job_data.get('source_url', '')),
                source_metadata={
                    'job_title': company_info['job_title'],
                    'location': company_info['location'],
                    'company_size': company_info['company_size'],
                    'search_based': True
                },
                confidence_level=confidence,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"Indeed job analysis"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from Indeed job: {e}")
            return None


class GlassdoorAdapter(JobBoardAdapter):
    """Glassdoor job board adapter using search-based discovery."""
    
    def __init__(self, config: Settings) -> None:
        """Initialize Glassdoor adapter."""
        super().__init__(config, LeadSourceType.GLASSDOOR)
    
    async def analyze_job_postings(self, job_keywords: List[str]) -> List[Lead]:
        """Analyze Glassdoor job postings for company leads.
        
        Args:
            job_keywords: Job search keywords.
            
        Returns:
            List of discovered leads from Glassdoor job postings.
        """
        logger.info("Starting Glassdoor search-based job analysis")
        
        all_leads = []
        processed_companies = set()
        
        for keyword in job_keywords:
            query = f"site:glassdoor.com {keyword} IoT embedded firmware engineer jobs"
            
            try:
                search_results = await self.search_agent.search(query, max_results=15)
                
                for result in search_results.results:
                    job_info = self._extract_job_from_search_result(result)
                    
                    if not job_info:
                        continue
                    
                    company_name = job_info.get('company', '')
                    if not company_name or company_name in processed_companies:
                        continue
                    
                    processed_companies.add(company_name)
                    
                    lead = self._create_lead_from_job(job_info)
                    if lead and lead.relevance_score and lead.relevance_score > 0.3:
                        all_leads.append(lead)
            
            except Exception as e:
                logger.error(f"Glassdoor search failed for keyword '{keyword}': {e}")
                continue
        
        logger.info(f"Glassdoor analysis completed: {len(all_leads)} leads")
        return all_leads
    
    def _extract_job_from_search_result(self, result) -> Optional[Dict[str, Any]]:
        """Extract job information from Glassdoor search result.
        
        Args:
            result: Search result object.
            
        Returns:
            Job information dictionary if valid, None otherwise.
        """
        try:
            title = result.title
            snippet = result.snippet or ''
            
            # Extract job title and company from title
            # Glassdoor format varies, try multiple patterns
            patterns = [
                r'^([^-]+?)\s*-\s*([^-]+?)(?:\s*-|$)',  # "Job Title - Company Name"
                r'^([^|]+?)\s*\|\s*([^|]+?)(?:\s*\||$)',  # "Job Title | Company Name"
                r'([^-]+?)\s+at\s+([^-\n]+)',  # "Job Title at Company Name"
            ]
            
            job_title = ''
            company_name = ''
            
            for pattern in patterns:
                match = re.search(pattern, title)
                if match:
                    job_title = match.group(1).strip()
                    company_name = match.group(2).strip()
                    break
            
            # Fallback: extract from snippet
            if not company_name:
                company_match = re.search(r'(?:Company|at)\s*:\s*([^-\n]+)', snippet)
                company_name = company_match.group(1).strip() if company_match else ''
            
            # Extract location from snippet
            location_match = re.search(r'(?:Location|in)\s*:\s*([^-\n]+)', snippet)
            location = location_match.group(1).strip() if location_match else ''
            
            if not company_name or not job_title:
                return None
            
            return {
                'title': job_title,
                'company': company_name,
                'description': snippet,
                'location': location,
                'posted_date': '',  # Not available from search results
                'company_url': '',  # Not directly available
                'source_url': str(result.url)
            }
            
        except Exception as e:
            logger.error(f"Error extracting Glassdoor job from search result: {e}")
            return None
    
    def _create_lead_from_job(self, job_data: Dict[str, Any]) -> Optional[Lead]:
        """Create lead from Glassdoor job data.
        
        Args:
            job_data: Job posting data.
            
        Returns:
            Lead object if valid, None otherwise.
        """
        try:
            # Extract company information
            company_info = self._extract_company_from_job(job_data)
            
            if not company_info['company_name']:
                return None
            
            # Calculate relevance score
            job_text = f"{job_data.get('title', '')} {job_data.get('description', '')}"
            relevance_score = self._calculate_iot_relevance(job_text)
            
            # Determine confidence (Glassdoor typically has good company data)
            confidence = self._determine_job_confidence(job_data, company_info, relevance_score)
            
            # Boost confidence slightly for Glassdoor due to company reviews/data
            if confidence == LeadConfidence.LOW:
                confidence = LeadConfidence.MEDIUM
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=f"glassdoor_job:{job_data.get('source_url', '')}",
                source_url=HttpUrl(job_data.get('source_url', '')),
                source_metadata={
                    'job_title': company_info['job_title'],
                    'location': company_info['location'],
                    'company_size': company_info['company_size'],
                    'search_based': True
                },
                confidence_level=confidence,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"Glassdoor job analysis"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from Glassdoor job: {e}")
            return None