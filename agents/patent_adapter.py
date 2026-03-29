"""Patent database mining adapter for lead discovery.

This module implements patent database analysis for discovering IoT and
embedded systems companies through USPTO and Google Patents.
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


class PatentAdapter:
    """Base class for patent database adapters."""
    
    def __init__(self, config: Settings, source_type: LeadSourceType) -> None:
        """Initialize patent adapter.
        
        Args:
            config: Application configuration settings.
            source_type: Type of patent source.
        """
        self.config = config
        self.source_type = source_type
        self.timeout = config.get_int('patents', 'timeout', fallback=30)
        self.max_retries = config.get_int('patents', 'max_retries', fallback=3)
        
        # Initialize search agent for search-based discovery
        self.search_agent = SearchAgent(config)
        
        # IoT/Embedded patent keywords
        self.iot_patent_keywords = [
            'internet of things', 'iot device', 'smart sensor', 'wireless sensor',
            'embedded system', 'microcontroller', 'firmware', 'edge computing',
            'industrial iot', 'connected device', 'sensor network', 'mesh network',
            'bluetooth low energy', 'zigbee', 'lora', 'lorawan', 'wifi module',
            'smart home', 'home automation', 'building automation', 'hvac control',
            'wearable device', 'fitness tracker', 'health monitor', 'medical device',
            'automotive sensor', 'vehicle telematics', 'fleet management',
            'agricultural sensor', 'precision agriculture', 'smart farming',
            'industrial automation', 'process control', 'scada', 'plc',
            'energy management', 'smart grid', 'smart meter', 'power monitoring'
        ]
        
        # Technology classification keywords
        self.tech_classifications = {
            'wireless_communication': ['wireless', 'bluetooth', 'wifi', 'cellular', 'lte', '5g', 'zigbee', 'lora'],
            'sensor_technology': ['sensor', 'accelerometer', 'gyroscope', 'temperature', 'pressure', 'humidity'],
            'embedded_systems': ['microcontroller', 'microprocessor', 'embedded', 'firmware', 'rtos'],
            'power_management': ['battery', 'power management', 'energy harvesting', 'low power'],
            'data_processing': ['data processing', 'edge computing', 'machine learning', 'analytics'],
            'security': ['encryption', 'authentication', 'secure', 'cybersecurity', 'privacy']
        }
    
    async def mine_patents(self, search_terms: List[str]) -> List[Lead]:
        """Mine patents for company leads.
        
        Args:
            search_terms: Patent search terms.
            
        Returns:
            List of discovered leads from patents.
        """
        raise NotImplementedError("Subclasses must implement mine_patents method")
    
    def _calculate_iot_relevance(self, text: str) -> float:
        """Calculate IoT/embedded systems relevance score for patent text.
        
        Args:
            text: Patent text to analyze.
            
        Returns:
            Relevance score between 0.0 and 1.0.
        """
        if not text:
            return 0.0
        
        text_lower = text.lower()
        matches = sum(1 for keyword in self.iot_patent_keywords if keyword in text_lower)
        
        # Calculate base score
        base_score = min(matches / len(self.iot_patent_keywords), 1.0)
        
        # Boost for high-value keywords
        high_value_keywords = ['internet of things', 'iot device', 'embedded system', 'industrial iot']
        boost = sum(0.15 for keyword in high_value_keywords if keyword in text_lower)
        
        return min(base_score + boost, 1.0)
    
    def _extract_assignee_info(self, assignee_name: str, patent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract company information from patent assignee data.
        
        Args:
            assignee_name: Name of patent assignee.
            patent_data: Patent data dictionary.
            
        Returns:
            Dictionary with extracted company information.
        """
        # Clean up assignee name
        company_name = self._clean_assignee_name(assignee_name)
        
        # Extract potential website from assignee name or patent data
        company_url = None
        domain = None
        
        # Look for website patterns in assignee name
        website_match = re.search(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', assignee_name.lower())
        if website_match:
            potential_domain = website_match.group(1)
            potential_url = f'https://{potential_domain}'
            if validate_url(potential_url):
                company_url = HttpUrl(potential_url)
                domain = validate_domain(potential_domain)
        
        # Extract technology classifications
        patent_text = f"{patent_data.get('title', '')} {patent_data.get('abstract', '')}"
        technology_tags = self._classify_patent_technology(patent_text)
        
        # Extract industry tags based on patent content
        industry_tags = self._extract_patent_industry_tags(patent_text)
        
        # Create description from patent abstract
        description = patent_data.get('abstract', '')[:500] if patent_data.get('abstract') else ''
        
        return {
            'company_name': company_name,
            'company_url': company_url,
            'domain': domain,
            'description': description,
            'industry_tags': industry_tags,
            'technology_tags': technology_tags,
            'contact_emails': []  # Patents typically don't contain direct email contacts
        }
    
    def _clean_assignee_name(self, assignee_name: str) -> str:
        """Clean and normalize assignee name to extract company name.
        
        Args:
            assignee_name: Raw assignee name from patent.
            
        Returns:
            Cleaned company name.
        """
        if not assignee_name:
            return ''
        
        # Remove common suffixes and prefixes
        name = assignee_name.strip()
        
        # Remove location information in parentheses
        name = re.sub(r'\([^)]*\)', '', name).strip()
        
        # Remove common corporate suffixes for normalization
        suffixes = [
            r'\s+inc\.?$', r'\s+incorporated$', r'\s+corp\.?$', r'\s+corporation$',
            r'\s+ltd\.?$', r'\s+limited$', r'\s+llc$', r'\s+co\.?$', r'\s+company$',
            r'\s+gmbh$', r'\s+ag$', r'\s+sa$', r'\s+bv$', r'\s+oy$', r'\s+ab$'
        ]
        
        for suffix in suffixes:
            name = re.sub(suffix, '', name, flags=re.IGNORECASE).strip()
        
        return name
    
    def _classify_patent_technology(self, patent_text: str) -> List[str]:
        """Classify patent technology based on content.
        
        Args:
            patent_text: Patent title and abstract text.
            
        Returns:
            List of technology classification tags.
        """
        text_lower = patent_text.lower()
        found_tags = []
        
        for tech_category, keywords in self.tech_classifications.items():
            if any(keyword in text_lower for keyword in keywords):
                found_tags.append(tech_category)
        
        return found_tags
    
    def _extract_patent_industry_tags(self, patent_text: str) -> List[str]:
        """Extract industry tags from patent content.
        
        Args:
            patent_text: Patent title and abstract text.
            
        Returns:
            List of industry tags.
        """
        text_lower = patent_text.lower()
        
        industry_keywords = {
            'automotive': ['automotive', 'vehicle', 'car', 'truck', 'transportation', 'telematics'],
            'healthcare': ['medical', 'health', 'patient', 'diagnostic', 'therapeutic', 'clinical'],
            'industrial': ['industrial', 'manufacturing', 'factory', 'process control', 'automation'],
            'consumer_electronics': ['consumer', 'smartphone', 'tablet', 'wearable', 'smart watch'],
            'smart_home': ['home automation', 'smart home', 'building', 'hvac', 'lighting'],
            'agriculture': ['agricultural', 'farming', 'crop', 'livestock', 'irrigation', 'greenhouse'],
            'energy': ['energy', 'power', 'solar', 'wind', 'battery', 'grid', 'utility'],
            'security': ['security', 'surveillance', 'access control', 'monitoring', 'alarm'],
            'telecommunications': ['telecommunication', 'network', 'cellular', 'base station', 'antenna']
        }
        
        found_tags = []
        for industry, keywords in industry_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                found_tags.append(industry)
        
        return found_tags
    
    def _determine_patent_confidence(self, patent_data: Dict[str, Any], 
                                   assignee_name: str, relevance_score: float) -> LeadConfidence:
        """Determine confidence level for a patent-derived lead.
        
        Args:
            patent_data: Patent information.
            assignee_name: Patent assignee name.
            relevance_score: IoT relevance score.
            
        Returns:
            Confidence level enumeration.
        """
        confidence_score = 0
        
        # Patent recency (more recent = higher confidence)
        patent_date = patent_data.get('publication_date', '')
        if patent_date:
            try:
                pub_date = datetime.strptime(patent_date[:10], '%Y-%m-%d')
                years_old = (datetime.now() - pub_date).days / 365.25
                if years_old <= 2:
                    confidence_score += 2
                elif years_old <= 5:
                    confidence_score += 1
            except:
                pass
        
        # Assignee type (corporations typically higher confidence than individuals)
        if any(indicator in assignee_name.lower() for indicator in 
               ['inc', 'corp', 'ltd', 'llc', 'gmbh', 'company', 'technologies']):
            confidence_score += 2
        
        # IoT relevance
        if relevance_score >= 0.7:
            confidence_score += 2
        elif relevance_score >= 0.4:
            confidence_score += 1
        
        # Patent complexity (longer abstracts typically indicate more substantial inventions)
        abstract_length = len(patent_data.get('abstract', ''))
        if abstract_length > 500:
            confidence_score += 1
        
        # Map score to confidence level
        if confidence_score >= 5:
            return LeadConfidence.HIGH
        elif confidence_score >= 3:
            return LeadConfidence.MEDIUM
        else:
            return LeadConfidence.LOW


class USPTOAdapter(PatentAdapter):
    """USPTO patent database adapter."""
    
    def __init__(self, config: Settings) -> None:
        """Initialize USPTO adapter."""
        super().__init__(config, LeadSourceType.USPTO_PATENTS)
        
        # USPTO doesn't require API key for basic searches
        self.base_url = 'https://developer.uspto.gov/api/v1'
        
        # Rate limiter: USPTO allows reasonable request rates
        from agents.rate_limiter import RateLimitConfig, RateLimiter
        rate_config = RateLimitConfig(requests_per_window=30, window_seconds=60)
        self.rate_limiter = RateLimiter(rate_config)
    
    async def mine_patents(self, search_terms: List[str]) -> List[Lead]:
        """Mine USPTO patents for company leads.
        
        Args:
            search_terms: Patent search terms.
            
        Returns:
            List of discovered leads from USPTO patents.
        """
        logger.info("Starting USPTO patent mining")
        
        all_leads = []
        processed_assignees = set()
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for search_term in search_terms:
                try:
                    patents = await self._search_uspto_patents(client, search_term)
                    
                    for patent in patents:
                        assignees = patent.get('assignees', [])
                        
                        for assignee in assignees:
                            assignee_name = assignee.get('name', '')
                            
                            # Skip if already processed or not a company
                            if not assignee_name or assignee_name in processed_assignees:
                                continue
                            
                            if not self._is_company_assignee(assignee_name):
                                continue
                            
                            processed_assignees.add(assignee_name)
                            
                            lead = self._create_lead_from_patent(patent, assignee_name)
                            if lead and lead.relevance_score and lead.relevance_score > 0.3:
                                all_leads.append(lead)
                
                except Exception as e:
                    logger.error(f"Error processing USPTO search term '{search_term}': {e}")
                    continue
        
        logger.info(f"USPTO patent mining completed: {len(all_leads)} leads")
        return all_leads
    
    async def _search_uspto_patents(self, client: httpx.AsyncClient, 
                                  search_term: str) -> List[Dict[str, Any]]:
        """Search USPTO patents for a specific term.
        
        Args:
            client: HTTP client for API requests.
            search_term: Patent search term.
            
        Returns:
            List of patent data dictionaries.
        """
        await self.rate_limiter.acquire()
        
        # Build search parameters
        params = {
            'searchText': f'({search_term}) AND (IoT OR "internet of things" OR embedded OR sensor)',
            'start': 0,
            'rows': 50,  # Limit results per query
            'sort': 'date desc'  # Most recent first
        }
        
        try:
            response = await client.get(
                f'{self.base_url}/search',
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            patents = data.get('results', [])
            
            logger.debug(f"Found {len(patents)} USPTO patents for term: {search_term}")
            return patents
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError("USPTO API rate limit exceeded")
            raise APIError(f"USPTO patent search failed: {e}")
        except Exception as e:
            # Fallback to search-based discovery if API fails
            logger.warning(f"USPTO API search failed, falling back to search: {e}")
            return await self._search_based_patent_discovery(search_term)
    
    async def _search_based_patent_discovery(self, search_term: str) -> List[Dict[str, Any]]:
        """Fallback search-based patent discovery for USPTO.
        
        Args:
            search_term: Search term for patents.
            
        Returns:
            List of patent-like data extracted from search results.
        """
        query = f"site:patents.uspto.gov {search_term} IoT embedded sensor"
        
        try:
            search_results = await self.search_agent.search(query, max_results=20)
            patents = []
            
            for result in search_results.results:
                # Extract patent information from search result
                patent_info = self._extract_patent_from_search_result(result)
                if patent_info:
                    patents.append(patent_info)
            
            return patents
            
        except Exception as e:
            logger.error(f"Search-based USPTO patent discovery failed: {e}")
            return []
    
    def _extract_patent_from_search_result(self, result) -> Optional[Dict[str, Any]]:
        """Extract patent information from search result.
        
        Args:
            result: Search result object.
            
        Returns:
            Patent information dictionary if valid, None otherwise.
        """
        try:
            title = result.title
            snippet = result.snippet or ''
            
            # Extract patent number from URL or title
            patent_match = re.search(r'(\d{7,10})', str(result.url))
            patent_number = patent_match.group(1) if patent_match else ''
            
            # Extract assignee from snippet (usually after "Assignee:" or "Inventor:")
            assignee_match = re.search(r'(?:Assignee|Inventor):\s*([^,\n]+)', snippet)
            assignee = assignee_match.group(1).strip() if assignee_match else ''
            
            if not title or not assignee:
                return None
            
            return {
                'patent_number': patent_number,
                'title': title,
                'abstract': snippet,
                'assignees': [{'name': assignee}],
                'publication_date': '',  # Not available from search results
                'url': str(result.url)
            }
            
        except Exception as e:
            logger.error(f"Error extracting patent from search result: {e}")
            return None
    
    def _create_lead_from_patent(self, patent: Dict[str, Any], assignee_name: str) -> Optional[Lead]:
        """Create lead from USPTO patent data.
        
        Args:
            patent: Patent data dictionary.
            assignee_name: Patent assignee name.
            
        Returns:
            Lead object if valid, None otherwise.
        """
        try:
            # Extract company information
            company_info = self._extract_assignee_info(assignee_name, patent)
            
            if not company_info['company_name']:
                return None
            
            # Calculate relevance score
            patent_text = f"{patent.get('title', '')} {patent.get('abstract', '')}"
            relevance_score = self._calculate_iot_relevance(patent_text)
            
            # Determine confidence
            confidence = self._determine_patent_confidence(patent, assignee_name, relevance_score)
            
            # Build patent URL
            patent_number = patent.get('patent_number', '')
            patent_url = f"https://patents.uspto.gov/patent/{patent_number}" if patent_number else patent.get('url', '')
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=patent_number,
                source_url=HttpUrl(patent_url) if patent_url else None,
                source_metadata={
                    'patent_number': patent_number,
                    'patent_title': patent.get('title', ''),
                    'publication_date': patent.get('publication_date', ''),
                    'assignee_name': assignee_name
                },
                confidence_level=confidence,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"USPTO patent search"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from USPTO patent: {e}")
            return None
    
    def _is_company_assignee(self, assignee_name: str) -> bool:
        """Check if assignee appears to be a company rather than an individual.
        
        Args:
            assignee_name: Assignee name to check.
            
        Returns:
            True if appears to be a company, False otherwise.
        """
        if not assignee_name:
            return False
        
        name_lower = assignee_name.lower()
        
        # Company indicators
        company_indicators = [
            'inc', 'corp', 'corporation', 'ltd', 'limited', 'llc', 'company',
            'technologies', 'systems', 'solutions', 'gmbh', 'ag', 'sa', 'bv'
        ]
        
        # Individual indicators (to exclude)
        individual_indicators = [
            'university', 'college', 'institute', 'research', 'government'
        ]
        
        # Check for company indicators
        has_company_indicator = any(indicator in name_lower for indicator in company_indicators)
        
        # Check for individual/institution indicators
        has_individual_indicator = any(indicator in name_lower for indicator in individual_indicators)
        
        return has_company_indicator and not has_individual_indicator


class GooglePatentsAdapter(PatentAdapter):
    """Google Patents adapter using search-based discovery."""
    
    def __init__(self, config: Settings) -> None:
        """Initialize Google Patents adapter."""
        super().__init__(config, LeadSourceType.GOOGLE_PATENTS)
    
    async def mine_patents(self, search_terms: List[str]) -> List[Lead]:
        """Mine Google Patents for company leads using search-based approach.
        
        Google Patents doesn't have a public API, so we use search-based discovery.
        
        Args:
            search_terms: Patent search terms.
            
        Returns:
            List of discovered leads from Google Patents.
        """
        logger.info("Starting Google Patents search-based mining")
        
        all_leads = []
        processed_assignees = set()
        
        for search_term in search_terms:
            query = f"site:patents.google.com {search_term} IoT embedded sensor assignee"
            
            try:
                search_results = await self.search_agent.search(query, max_results=25)
                
                for result in search_results.results:
                    patent_info = self._extract_patent_from_search_result(result)
                    
                    if not patent_info:
                        continue
                    
                    assignees = patent_info.get('assignees', [])
                    for assignee in assignees:
                        assignee_name = assignee.get('name', '')
                        
                        if (not assignee_name or assignee_name in processed_assignees or 
                            not self._is_company_assignee(assignee_name)):
                            continue
                        
                        processed_assignees.add(assignee_name)
                        
                        lead = self._create_lead_from_patent(patent_info, assignee_name)
                        if lead and lead.relevance_score and lead.relevance_score > 0.3:
                            all_leads.append(lead)
            
            except Exception as e:
                logger.error(f"Google Patents search failed for term '{search_term}': {e}")
                continue
        
        logger.info(f"Google Patents mining completed: {len(all_leads)} leads")
        return all_leads
    
    def _extract_patent_from_search_result(self, result) -> Optional[Dict[str, Any]]:
        """Extract patent information from Google Patents search result.
        
        Args:
            result: Search result object.
            
        Returns:
            Patent information dictionary if valid, None otherwise.
        """
        try:
            title = result.title
            snippet = result.snippet or ''
            
            # Extract patent number from URL
            patent_match = re.search(r'/patent/([A-Z0-9]+)', str(result.url))
            patent_number = patent_match.group(1) if patent_match else ''
            
            # Extract assignee information from snippet
            assignees = []
            
            # Look for "Assignee:" pattern
            assignee_match = re.search(r'Assignee:\s*([^-\n]+)', snippet)
            if assignee_match:
                assignee_name = assignee_match.group(1).strip()
                assignees.append({'name': assignee_name})
            
            # Look for company names in snippet (fallback)
            if not assignees:
                company_patterns = [
                    r'([A-Z][a-zA-Z\s&.-]+(?:Inc|Corp|Ltd|LLC|GmbH|Technologies|Systems|Solutions))',
                    r'([A-Z][a-zA-Z\s&.-]{5,30})\s*(?:-|,|\n)'
                ]
                
                for pattern in company_patterns:
                    matches = re.findall(pattern, snippet)
                    for match in matches[:2]:  # Limit to first 2 matches
                        assignees.append({'name': match.strip()})
            
            if not title or not assignees:
                return None
            
            return {
                'patent_number': patent_number,
                'title': title,
                'abstract': snippet,
                'assignees': assignees,
                'publication_date': '',  # Not available from search results
                'url': str(result.url)
            }
            
        except Exception as e:
            logger.error(f"Error extracting Google Patents data from search result: {e}")
            return None
    
    def _create_lead_from_patent(self, patent: Dict[str, Any], assignee_name: str) -> Optional[Lead]:
        """Create lead from Google Patents data.
        
        Args:
            patent: Patent data dictionary.
            assignee_name: Patent assignee name.
            
        Returns:
            Lead object if valid, None otherwise.
        """
        try:
            # Extract company information
            company_info = self._extract_assignee_info(assignee_name, patent)
            
            if not company_info['company_name']:
                return None
            
            # Calculate relevance score
            patent_text = f"{patent.get('title', '')} {patent.get('abstract', '')}"
            relevance_score = self._calculate_iot_relevance(patent_text)
            
            # Determine confidence
            confidence = self._determine_patent_confidence(patent, assignee_name, relevance_score)
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=patent.get('patent_number', ''),
                source_url=HttpUrl(patent.get('url', '')),
                source_metadata={
                    'patent_number': patent.get('patent_number', ''),
                    'patent_title': patent.get('title', ''),
                    'assignee_name': assignee_name,
                    'search_based': True
                },
                confidence_level=confidence,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"Google Patents search"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from Google Patents data: {e}")
            return None
    
    def _is_company_assignee(self, assignee_name: str) -> bool:
        """Check if assignee appears to be a company rather than an individual.
        
        Args:
            assignee_name: Assignee name to check.
            
        Returns:
            True if appears to be a company, False otherwise.
        """
        if not assignee_name:
            return False
        
        name_lower = assignee_name.lower()
        
        # Company indicators
        company_indicators = [
            'inc', 'corp', 'corporation', 'ltd', 'limited', 'llc', 'company',
            'technologies', 'systems', 'solutions', 'gmbh', 'ag', 'sa', 'bv',
            'co.', 'co,', 'oy', 'ab'
        ]
        
        # Individual/institution indicators (to exclude)
        exclude_indicators = [
            'university', 'college', 'institute', 'research center', 'government',
            'ministry', 'department', 'agency', 'foundation', 'hospital'
        ]
        
        # Check for company indicators
        has_company_indicator = any(indicator in name_lower for indicator in company_indicators)
        
        # Check for exclusion indicators
        has_exclude_indicator = any(indicator in name_lower for indicator in exclude_indicators)
        
        # Additional heuristic: if name has multiple capital words, likely a company
        capital_words = len(re.findall(r'\b[A-Z][a-z]+', assignee_name))
        likely_company_name = capital_words >= 2 and len(assignee_name) > 10
        
        return (has_company_indicator or likely_company_name) and not has_exclude_indicator