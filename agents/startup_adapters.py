"""Startup directory adapters for lead discovery.

This module implements adapters for various startup directories and databases
including Product Hunt, AngelList, Crunchbase, F6S, and Gust.
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
from utils.exceptions import APIError, RateLimitError, ConfigurationError
from utils.validators import validate_url, validate_domain


logger = logging.getLogger(__name__)


class StartupDirectoryAdapter:
    """Base class for startup directory adapters."""
    
    def __init__(self, config: Settings, source_type: LeadSourceType) -> None:
        """Initialize startup directory adapter.
        
        Args:
            config: Application configuration settings.
            source_type: Type of startup directory source.
        """
        self.config = config
        self.source_type = source_type
        self.timeout = config.get_int('startup_directories', 'timeout', fallback=30)
        self.max_retries = config.get_int('startup_directories', 'max_retries', fallback=3)
        
        # Initialize search agent for fallback search-based discovery
        self.search_agent = SearchAgent(config)
        
        # IoT/Embedded relevance keywords
        self.iot_keywords = [
            'iot', 'internet of things', 'embedded', 'hardware', 'sensor',
            'smart device', 'connected device', 'industrial iot', 'edge computing',
            'firmware', 'microcontroller', 'arduino', 'raspberry pi', 'wearable',
            'smart home', 'automation', 'robotics', 'drone', 'wireless'
        ]
    
    async def discover_leads(self, categories: List[str]) -> List[Lead]:
        """Discover leads from startup directory.
        
        Args:
            categories: Search categories for discovery.
            
        Returns:
            List of discovered leads.
        """
        raise NotImplementedError("Subclasses must implement discover_leads method")
    
    def _calculate_iot_relevance(self, text: str) -> float:
        """Calculate IoT/embedded systems relevance score.
        
        Args:
            text: Text to analyze for IoT relevance.
            
        Returns:
            Relevance score between 0.0 and 1.0.
        """
        if not text:
            return 0.0
        
        text_lower = text.lower()
        matches = sum(1 for keyword in self.iot_keywords if keyword in text_lower)
        
        # Calculate base score
        base_score = min(matches / len(self.iot_keywords), 1.0)
        
        # Boost for high-value keywords
        high_value_keywords = ['iot', 'embedded', 'hardware', 'industrial iot']
        boost = sum(0.1 for keyword in high_value_keywords if keyword in text_lower)
        
        return min(base_score + boost, 1.0)
    
    def _extract_company_info(self, name: str, description: str, website: str) -> Dict[str, Any]:
        """Extract and normalize company information.
        
        Args:
            name: Company name.
            description: Company description.
            website: Company website URL.
            
        Returns:
            Dictionary with normalized company information.
        """
        # Normalize company name
        company_name = name.strip() if name else ''
        
        # Normalize and validate website URL
        company_url = None
        domain = None
        
        if website:
            # Clean up URL
            if not website.startswith(('http://', 'https://')):
                website = f'https://{website}'
            
            if validate_url(website):
                company_url = HttpUrl(website)
                domain = validate_domain(urlparse(website).netloc)
        
        # Extract industry and technology tags
        all_text = f"{name} {description}".lower()
        industry_tags = self._extract_industry_tags(all_text)
        technology_tags = self._extract_technology_tags(all_text)
        
        # Extract contact emails from description
        contact_emails = self._extract_emails(description)
        
        return {
            'company_name': company_name,
            'company_url': company_url,
            'domain': domain,
            'description': description.strip() if description else '',
            'industry_tags': industry_tags,
            'technology_tags': technology_tags,
            'contact_emails': contact_emails
        }
    
    def _extract_industry_tags(self, text: str) -> List[str]:
        """Extract industry tags from text."""
        industry_keywords = {
            'automotive': ['automotive', 'car', 'vehicle', 'transportation', 'mobility'],
            'healthcare': ['healthcare', 'medical', 'health', 'patient', 'telemedicine'],
            'industrial': ['industrial', 'manufacturing', 'factory', 'automation', 'industry 4.0'],
            'smart_home': ['smart home', 'home automation', 'smart building', 'connected home'],
            'agriculture': ['agriculture', 'farming', 'agtech', 'precision agriculture'],
            'energy': ['energy', 'renewable', 'solar', 'wind', 'smart grid', 'battery'],
            'retail': ['retail', 'e-commerce', 'shopping', 'point of sale', 'inventory'],
            'logistics': ['logistics', 'supply chain', 'shipping', 'tracking', 'warehouse'],
            'fintech': ['fintech', 'financial', 'payment', 'banking', 'cryptocurrency'],
            'security': ['security', 'surveillance', 'access control', 'cybersecurity']
        }
        
        found_tags = []
        for tag, keywords in industry_keywords.items():
            if any(keyword in text for keyword in keywords):
                found_tags.append(tag)
        
        return found_tags
    
    def _extract_technology_tags(self, text: str) -> List[str]:
        """Extract technology tags from text."""
        tech_keywords = {
            'mobile': ['mobile', 'ios', 'android', 'app'],
            'web': ['web', 'saas', 'platform', 'dashboard'],
            'ai_ml': ['ai', 'artificial intelligence', 'machine learning', 'ml', 'deep learning'],
            'cloud': ['cloud', 'aws', 'azure', 'gcp', 'serverless'],
            'blockchain': ['blockchain', 'crypto', 'bitcoin', 'ethereum', 'web3'],
            'api': ['api', 'integration', 'sdk', 'webhook'],
            'analytics': ['analytics', 'data', 'insights', 'reporting', 'dashboard'],
            'hardware': ['hardware', 'device', 'sensor', 'embedded', 'firmware']
        }
        
        found_tags = []
        for tag, keywords in tech_keywords.items():
            if any(keyword in text for keyword in keywords):
                found_tags.append(tag)
        
        return found_tags
    
    def _extract_emails(self, text: str) -> List[str]:
        """Extract email addresses from text."""
        if not text:
            return []
        
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        
        # Filter valid business emails
        valid_emails = []
        from config.constants import EXCLUDED_DOMAINS
        exclude_domains = EXCLUDED_DOMAINS
        
        for email in emails:
            domain = email.split('@')[1].lower()
            if domain not in exclude_domains:
                valid_emails.append(email.lower())
        
        return list(set(valid_emails))


class ProductHuntAdapter(StartupDirectoryAdapter):
    """Product Hunt adapter for startup discovery."""
    
    def __init__(self, config: Settings) -> None:
        """Initialize Product Hunt adapter."""
        super().__init__(config, LeadSourceType.PRODUCT_HUNT)
        
        self.api_token = config.get_secure('product_hunt', 'api_token')
        self.base_url = 'https://api.producthunt.com/v2/api/graphql'
        
        # Rate limiter: Product Hunt allows 1000 requests/hour
        from agents.rate_limiter import RateLimitConfig, RateLimiter
        rate_config = RateLimitConfig(requests_per_window=16, window_seconds=60)
        self.rate_limiter = RateLimiter(rate_config)
    
    async def discover_leads(self, categories: List[str]) -> List[Lead]:
        """Discover leads from Product Hunt.
        
        Args:
            categories: Search categories (e.g., ['hardware', 'iot', 'smart-home']).
            
        Returns:
            List of discovered leads from Product Hunt.
        """
        if not self.api_token:
            logger.warning("Product Hunt API token not configured, using search-based discovery")
            return await self._search_based_discovery(categories)
        
        logger.info("Starting Product Hunt API-based discovery")
        
        all_leads = []
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for category in categories:
                try:
                    products = await self._fetch_products_by_category(client, category)
                    
                    for product in products:
                        lead = self._create_lead_from_product(product)
                        if lead and lead.relevance_score and lead.relevance_score > 0.3:
                            all_leads.append(lead)
                
                except Exception as e:
                    logger.error(f"Error fetching Product Hunt category '{category}': {e}")
                    continue
        
        logger.info(f"Product Hunt discovery completed: {len(all_leads)} leads")
        return all_leads
    
    async def _fetch_products_by_category(self, client: httpx.AsyncClient, 
                                        category: str) -> List[Dict[str, Any]]:
        """Fetch products from Product Hunt by category.
        
        Args:
            client: HTTP client for API requests.
            category: Product category to search.
            
        Returns:
            List of product data dictionaries.
        """
        await self.rate_limiter.acquire()
        
        # GraphQL query for products
        query = """
        query GetProducts($first: Int!, $after: String, $topic: String) {
            posts(first: $first, after: $after, topic: $topic) {
                edges {
                    node {
                        id
                        name
                        tagline
                        description
                        website
                        slug
                        votesCount
                        commentsCount
                        createdAt
                        makers {
                            name
                            headline
                        }
                        topics {
                            name
                        }
                    }
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """
        
        variables = {
            'first': 50,
            'topic': category
        }
        
        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = await client.post(
                self.base_url,
                json={'query': query, 'variables': variables},
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            
            if 'errors' in data:
                logger.error(f"Product Hunt GraphQL errors: {data['errors']}")
                return []
            
            posts = data.get('data', {}).get('posts', {}).get('edges', [])
            products = [edge['node'] for edge in posts]
            
            logger.debug(f"Fetched {len(products)} products for category: {category}")
            return products
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError("Product Hunt API rate limit exceeded")
            raise APIError(f"Product Hunt API request failed: {e}")
        except Exception as e:
            raise APIError(f"Product Hunt API error: {e}")
    
    def _create_lead_from_product(self, product: Dict[str, Any]) -> Optional[Lead]:
        """Create lead from Product Hunt product data.
        
        Args:
            product: Product data from Product Hunt API.
            
        Returns:
            Lead object if valid, None otherwise.
        """
        try:
            name = product.get('name', '')
            tagline = product.get('tagline', '')
            description = product.get('description', '')
            website = product.get('website', '')
            
            if not name or not website:
                return None
            
            # Combine description sources
            full_description = f"{tagline}. {description}".strip()
            
            # Extract company information
            company_info = self._extract_company_info(name, full_description, website)
            
            if not company_info['company_name']:
                return None
            
            # Calculate relevance score
            relevance_score = self._calculate_iot_relevance(full_description)
            
            # Determine confidence based on engagement
            votes = product.get('votesCount', 0)
            comments = product.get('commentsCount', 0)
            
            if votes >= 100 and comments >= 10:
                confidence = LeadConfidence.HIGH
            elif votes >= 20:
                confidence = LeadConfidence.MEDIUM
            else:
                confidence = LeadConfidence.LOW
            
            # Extract topics as additional tags
            topics = product.get('topics', [])
            topic_tags = [topic.get('name', '').lower() for topic in topics if topic.get('name')]
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'] + topic_tags,
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=product.get('id', ''),
                source_url=HttpUrl(f"https://www.producthunt.com/posts/{product.get('slug', '')}"),
                source_metadata={
                    'votes_count': votes,
                    'comments_count': comments,
                    'created_at': product.get('createdAt', ''),
                    'makers': product.get('makers', []),
                    'topics': topic_tags
                },
                confidence_level=confidence,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"Product Hunt category search"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from Product Hunt product: {e}")
            return None
    
    async def _search_based_discovery(self, categories: List[str]) -> List[Lead]:
        """Fallback search-based discovery for Product Hunt.
        
        Args:
            categories: Search categories.
            
        Returns:
            List of leads discovered through search.
        """
        leads = []
        
        for category in categories:
            query = f"site:producthunt.com {category} hardware IoT embedded"
            
            try:
                search_results = await self.search_agent.search(query, max_results=20)
                
                for result in search_results.results:
                    # Extract product information from search result
                    lead = self._create_lead_from_search_result(result)
                    if lead:
                        leads.append(lead)
            
            except Exception as e:
                logger.error(f"Search-based Product Hunt discovery failed for '{category}': {e}")
                continue
        
        return leads
    
    def _create_lead_from_search_result(self, result) -> Optional[Lead]:
        """Create lead from search result.
        
        Args:
            result: Search result object.
            
        Returns:
            Lead object if valid, None otherwise.
        """
        try:
            # Extract company name from title
            title = result.title
            snippet = result.snippet or ''
            
            # Look for company website in snippet
            website_match = re.search(r'https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', snippet)
            website = website_match.group(0) if website_match else ''
            
            if not title or not website:
                return None
            
            # Extract company information
            company_info = self._extract_company_info(title, snippet, website)
            
            if not company_info['company_name']:
                return None
            
            # Calculate relevance score
            relevance_score = self._calculate_iot_relevance(f"{title} {snippet}")
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=f"search:{result.url}",
                source_url=HttpUrl(str(result.url)),
                source_metadata={
                    'search_based': True,
                    'search_query': result.search_query
                },
                confidence_level=LeadConfidence.MEDIUM,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"Product Hunt search-based discovery"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from search result: {e}")
            return None


class CrunchbaseAdapter(StartupDirectoryAdapter):
    """Crunchbase adapter for startup discovery."""
    
    def __init__(self, config: Settings) -> None:
        """Initialize Crunchbase adapter."""
        super().__init__(config, LeadSourceType.CRUNCHBASE)
        
        self.api_key = config.get_secure('crunchbase', 'api_key')
        self.base_url = 'https://api.crunchbase.com/api/v4'
        
        # Rate limiter: Crunchbase has strict rate limits
        from agents.rate_limiter import RateLimitConfig, RateLimiter
        rate_config = RateLimitConfig(requests_per_window=30, window_seconds=60)
        self.rate_limiter = RateLimiter(rate_config)
    
    async def discover_leads(self, categories: List[str]) -> List[Lead]:
        """Discover leads from Crunchbase.
        
        Args:
            categories: Search categories.
            
        Returns:
            List of discovered leads from Crunchbase.
        """
        if not self.api_key:
            logger.warning("Crunchbase API key not configured, using search-based discovery")
            return await self._search_based_discovery(categories)
        
        logger.info("Starting Crunchbase API-based discovery")
        
        all_leads = []
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for category in categories:
                try:
                    organizations = await self._search_organizations(client, category)
                    
                    for org in organizations:
                        lead = await self._create_lead_from_organization(client, org)
                        if lead and lead.relevance_score and lead.relevance_score > 0.3:
                            all_leads.append(lead)
                
                except Exception as e:
                    logger.error(f"Error fetching Crunchbase category '{category}': {e}")
                    continue
        
        logger.info(f"Crunchbase discovery completed: {len(all_leads)} leads")
        return all_leads
    
    async def _search_organizations(self, client: httpx.AsyncClient, 
                                  category: str) -> List[Dict[str, Any]]:
        """Search organizations in Crunchbase by category.
        
        Args:
            client: HTTP client for API requests.
            category: Search category.
            
        Returns:
            List of organization data.
        """
        await self.rate_limiter.acquire()
        
        headers = {
            'X-cb-user-key': self.api_key,
            'Content-Type': 'application/json'
        }
        
        # Search parameters
        params = {
            'field_ids': 'identifier,name,short_description,website,categories',
            'query': category,
            'limit': 50
        }
        
        try:
            response = await client.get(
                f'{self.base_url}/searches/organizations',
                headers=headers,
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            entities = data.get('entities', [])
            
            logger.debug(f"Found {len(entities)} organizations for category: {category}")
            return [entity.get('properties', {}) for entity in entities]
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError("Crunchbase API rate limit exceeded")
            raise APIError(f"Crunchbase API request failed: {e}")
        except Exception as e:
            raise APIError(f"Crunchbase API error: {e}")
    
    async def _create_lead_from_organization(self, client: httpx.AsyncClient, 
                                           org: Dict[str, Any]) -> Optional[Lead]:
        """Create lead from Crunchbase organization data.
        
        Args:
            client: HTTP client for additional API requests.
            org: Organization data from Crunchbase.
            
        Returns:
            Lead object if valid, None otherwise.
        """
        try:
            name = org.get('name', '')
            description = org.get('short_description', '')
            website = org.get('website', '')
            
            if not name:
                return None
            
            # Extract company information
            company_info = self._extract_company_info(name, description, website)
            
            if not company_info['company_name']:
                return None
            
            # Calculate relevance score
            relevance_score = self._calculate_iot_relevance(description)
            
            # Extract categories as industry tags
            categories = org.get('categories', [])
            category_tags = []
            if isinstance(categories, list):
                for cat in categories:
                    if isinstance(cat, dict) and 'value' in cat:
                        category_tags.append(cat['value'].lower())
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'] + category_tags,
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=org.get('identifier', {}).get('value', ''),
                source_url=HttpUrl(f"https://www.crunchbase.com/organization/{org.get('identifier', {}).get('value', '')}"),
                source_metadata={
                    'categories': category_tags,
                    'crunchbase_url': f"https://www.crunchbase.com/organization/{org.get('identifier', {}).get('value', '')}"
                },
                confidence_level=LeadConfidence.HIGH,  # Crunchbase data is typically high quality
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"Crunchbase organization search"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from Crunchbase organization: {e}")
            return None
    
    async def _search_based_discovery(self, categories: List[str]) -> List[Lead]:
        """Fallback search-based discovery for Crunchbase.
        
        Args:
            categories: Search categories.
            
        Returns:
            List of leads discovered through search.
        """
        leads = []
        
        for category in categories:
            query = f"site:crunchbase.com {category} IoT hardware embedded startup"
            
            try:
                search_results = await self.search_agent.search(query, max_results=15)
                
                for result in search_results.results:
                    lead = self._create_lead_from_search_result(result)
                    if lead:
                        leads.append(lead)
            
            except Exception as e:
                logger.error(f"Search-based Crunchbase discovery failed for '{category}': {e}")
                continue
        
        return leads
    
    def _create_lead_from_search_result(self, result) -> Optional[Lead]:
        """Create lead from Crunchbase search result."""
        try:
            title = result.title
            snippet = result.snippet or ''
            
            # Extract company name from title (usually "CompanyName - Crunchbase")
            company_match = re.match(r'^([^-]+)', title)
            company_name = company_match.group(1).strip() if company_match else title
            
            # Look for website in snippet
            website_match = re.search(r'Website:\s*(https?://[^\s]+)', snippet)
            website = website_match.group(1) if website_match else ''
            
            if not company_name:
                return None
            
            # Extract company information
            company_info = self._extract_company_info(company_name, snippet, website)
            
            # Calculate relevance score
            relevance_score = self._calculate_iot_relevance(f"{title} {snippet}")
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=f"search:{result.url}",
                source_url=HttpUrl(str(result.url)),
                source_metadata={
                    'search_based': True,
                    'search_query': result.search_query
                },
                confidence_level=LeadConfidence.MEDIUM,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"Crunchbase search-based discovery"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from Crunchbase search result: {e}")
            return None


class F6SAdapter(StartupDirectoryAdapter):
    """F6S adapter for European startup discovery."""
    
    def __init__(self, config: Settings) -> None:
        """Initialize F6S adapter."""
        super().__init__(config, LeadSourceType.F6S)
    
    async def discover_leads(self, categories: List[str]) -> List[Lead]:
        """Discover leads from F6S using search-based approach.
        
        F6S doesn't have a public API, so we use search-based discovery.
        
        Args:
            categories: Search categories.
            
        Returns:
            List of discovered leads from F6S.
        """
        logger.info("Starting F6S search-based discovery")
        
        leads = []
        
        for category in categories:
            query = f"site:f6s.com {category} IoT hardware embedded startup Europe"
            
            try:
                search_results = await self.search_agent.search(query, max_results=15)
                
                for result in search_results.results:
                    lead = self._create_lead_from_search_result(result)
                    if lead:
                        leads.append(lead)
            
            except Exception as e:
                logger.error(f"F6S search discovery failed for '{category}': {e}")
                continue
        
        logger.info(f"F6S discovery completed: {len(leads)} leads")
        return leads
    
    def _create_lead_from_search_result(self, result) -> Optional[Lead]:
        """Create lead from F6S search result."""
        try:
            title = result.title
            snippet = result.snippet or ''
            
            # Extract company name from title
            company_name = title.split('-')[0].strip() if '-' in title else title
            
            # Look for website in snippet
            website_match = re.search(r'https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', snippet)
            website = website_match.group(0) if website_match else ''
            
            if not company_name:
                return None
            
            # Extract company information
            company_info = self._extract_company_info(company_name, snippet, website)
            
            # Calculate relevance score
            relevance_score = self._calculate_iot_relevance(f"{title} {snippet}")
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=f"search:{result.url}",
                source_url=HttpUrl(str(result.url)),
                source_metadata={
                    'search_based': True,
                    'search_query': result.search_query,
                    'region': 'Europe'
                },
                confidence_level=LeadConfidence.MEDIUM,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"F6S search-based discovery"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from F6S search result: {e}")
            return None


class GustAdapter(StartupDirectoryAdapter):
    """Gust adapter for global startup discovery."""
    
    def __init__(self, config: Settings) -> None:
        """Initialize Gust adapter."""
        super().__init__(config, LeadSourceType.GUST)
    
    async def discover_leads(self, categories: List[str]) -> List[Lead]:
        """Discover leads from Gust using search-based approach.
        
        Gust doesn't have a public API, so we use search-based discovery.
        
        Args:
            categories: Search categories.
            
        Returns:
            List of discovered leads from Gust.
        """
        logger.info("Starting Gust search-based discovery")
        
        leads = []
        
        for category in categories:
            query = f"site:gust.com {category} IoT hardware embedded technology startup"
            
            try:
                search_results = await self.search_agent.search(query, max_results=15)
                
                for result in search_results.results:
                    lead = self._create_lead_from_search_result(result)
                    if lead:
                        leads.append(lead)
            
            except Exception as e:
                logger.error(f"Gust search discovery failed for '{category}': {e}")
                continue
        
        logger.info(f"Gust discovery completed: {len(leads)} leads")
        return leads
    
    def _create_lead_from_search_result(self, result) -> Optional[Lead]:
        """Create lead from Gust search result."""
        try:
            title = result.title
            snippet = result.snippet or ''
            
            # Extract company name from title
            company_name = title.split('|')[0].strip() if '|' in title else title
            
            # Look for website in snippet
            website_match = re.search(r'Website:\s*(https?://[^\s]+)', snippet)
            website = website_match.group(1) if website_match else ''
            
            if not company_name:
                return None
            
            # Extract company information
            company_info = self._extract_company_info(company_name, snippet, website)
            
            # Calculate relevance score
            relevance_score = self._calculate_iot_relevance(f"{title} {snippet}")
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=f"search:{result.url}",
                source_url=HttpUrl(str(result.url)),
                source_metadata={
                    'search_based': True,
                    'search_query': result.search_query
                },
                confidence_level=LeadConfidence.MEDIUM,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"Gust search-based discovery"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from Gust search result: {e}")
            return None


class AngelListAdapter(StartupDirectoryAdapter):
    """AngelList (Wellfound) adapter for startup discovery."""
    
    def __init__(self, config: Settings) -> None:
        """Initialize AngelList adapter."""
        super().__init__(config, LeadSourceType.ANGELLIST)
    
    async def discover_leads(self, categories: List[str]) -> List[Lead]:
        """Discover leads from AngelList using search-based approach.
        
        AngelList API access is limited, so we use search-based discovery.
        
        Args:
            categories: Search categories.
            
        Returns:
            List of discovered leads from AngelList.
        """
        logger.info("Starting AngelList search-based discovery")
        
        leads = []
        
        for category in categories:
            # Search both old AngelList and new Wellfound domains
            queries = [
                f"site:angel.co {category} IoT hardware embedded startup",
                f"site:wellfound.com {category} IoT hardware embedded startup"
            ]
            
            for query in queries:
                try:
                    search_results = await self.search_agent.search(query, max_results=10)
                    
                    for result in search_results.results:
                        lead = self._create_lead_from_search_result(result)
                        if lead:
                            leads.append(lead)
                
                except Exception as e:
                    logger.error(f"AngelList search discovery failed for query '{query}': {e}")
                    continue
        
        logger.info(f"AngelList discovery completed: {len(leads)} leads")
        return leads
    
    def _create_lead_from_search_result(self, result) -> Optional[Lead]:
        """Create lead from AngelList search result."""
        try:
            title = result.title
            snippet = result.snippet or ''
            
            # Extract company name from title (usually "CompanyName - AngelList")
            company_match = re.match(r'^([^-|]+)', title)
            company_name = company_match.group(1).strip() if company_match else title
            
            # Look for website in snippet
            website_match = re.search(r'https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', snippet)
            website = website_match.group(0) if website_match else ''
            
            if not company_name:
                return None
            
            # Extract company information
            company_info = self._extract_company_info(company_name, snippet, website)
            
            # Calculate relevance score
            relevance_score = self._calculate_iot_relevance(f"{title} {snippet}")
            
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=self.source_type,
                source_id=f"search:{result.url}",
                source_url=HttpUrl(str(result.url)),
                source_metadata={
                    'search_based': True,
                    'search_query': result.search_query
                },
                confidence_level=LeadConfidence.MEDIUM,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"AngelList search-based discovery"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error creating lead from AngelList search result: {e}")
            return None