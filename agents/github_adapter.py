"""GitHub mining adapter for lead discovery.

This module implements GitHub repository and organization analysis
for discovering IoT and embedded systems companies.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urlparse, urljoin
import logging

import httpx
from pydantic import HttpUrl

from agents.models import Lead, LeadSourceType, LeadConfidence
from agents.rate_limiter import RateLimiter
from config.settings import Settings
from utils.exceptions import APIError, RateLimitError
from utils.validators import validate_url, validate_domain


logger = logging.getLogger(__name__)


class GitHubAdapter:
    """GitHub mining adapter for lead discovery.
    
    Discovers IoT and embedded systems companies through:
    - Repository search for relevant keywords
    - Organization analysis for commercial projects
    - README parsing for company information
    - Contributor analysis for business contacts
    """
    
    def __init__(self, config: Settings) -> None:
        """Initialize GitHub adapter.
        
        Args:
            config: Application configuration settings.
        """
        self.config = config
        self.api_token = config.get_secure('github', 'api_token')
        self.base_url = 'https://api.github.com'
        
        # Rate limiter: GitHub allows 5000 requests/hour for authenticated users
        requests_per_hour = 4800 if self.api_token else 60  # Conservative limits
        from agents.rate_limiter import RateLimitConfig, RateLimiter
        rate_config = RateLimitConfig(
            requests_per_window=requests_per_hour // 60,
            window_seconds=60
        )
        self.rate_limiter = RateLimiter(rate_config)
        
        # HTTP client configuration
        self.timeout = config.get_int('github', 'timeout', fallback=30)
        self.max_retries = config.get_int('github', 'max_retries', fallback=3)
        
        # Search configuration
        self.max_results_per_query = config.get_int('github', 'max_results_per_query', fallback=100)
        self.min_stars = config.get_int('github', 'min_stars', fallback=5)
        self.min_forks = config.get_int('github', 'min_forks', fallback=2)
        
        # Company detection patterns
        self.company_patterns = [
            r'(?i)(?:company|corp|corporation|inc|ltd|llc|gmbh|ag|sa|bv|oy|ab)(?:\s|$)',
            r'(?i)(?:technologies|technology|tech|solutions|systems|software|hardware)',
            r'(?i)(?:www\.|https?://)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        ]
        
        # IoT/Embedded keywords for relevance scoring
        self.iot_keywords = [
            'iot', 'internet of things', 'embedded', 'microcontroller', 'arduino',
            'raspberry pi', 'esp32', 'esp8266', 'sensor', 'actuator', 'firmware',
            'rtos', 'freertos', 'zephyr', 'mbed', 'contiki', 'riot', 'tinyos',
            'bluetooth', 'wifi', 'zigbee', 'lora', 'lorawan', 'mqtt', 'coap',
            'industrial iot', 'iiot', 'smart home', 'smart city', 'wearable',
            'edge computing', 'fog computing', 'mesh network', 'wireless sensor'
        ]
    
    async def discover_from_github(self, keywords: List[str]) -> List[Lead]:
        """Discover leads from GitHub repositories and organizations.
        
        Args:
            keywords: Search keywords for repository discovery.
            
        Returns:
            List of discovered leads with GitHub source attribution.
            
        Raises:
            APIError: If GitHub API requests fail.
            RateLimitError: If rate limits are exceeded.
        """
        logger.info(f"Starting GitHub discovery with {len(keywords)} keywords")
        
        all_leads = []
        processed_repos = set()
        processed_orgs = set()
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Search repositories for each keyword
            for keyword in keywords:
                try:
                    repos = await self._search_repositories(client, keyword)
                    
                    for repo in repos:
                        repo_id = repo.get('full_name')
                        if repo_id in processed_repos:
                            continue
                        processed_repos.add(repo_id)
                        
                        # Extract lead from repository
                        lead = await self._extract_lead_from_repo(client, repo)
                        if lead:
                            all_leads.append(lead)
                        
                        # Extract organization if not processed
                        org_login = repo.get('owner', {}).get('login')
                        org_type = repo.get('owner', {}).get('type')
                        
                        if org_type == 'Organization' and org_login not in processed_orgs:
                            processed_orgs.add(org_login)
                            org_lead = await self._extract_lead_from_org(client, org_login)
                            if org_lead:
                                all_leads.append(org_lead)
                
                except Exception as e:
                    logger.error(f"Error processing keyword '{keyword}': {e}")
                    continue
        
        # Deduplicate and score leads
        unique_leads = self._deduplicate_leads(all_leads)
        scored_leads = self._score_leads(unique_leads)
        
        logger.info(f"GitHub discovery completed: {len(scored_leads)} unique leads")
        return scored_leads
    
    async def _search_repositories(self, client: httpx.AsyncClient, keyword: str) -> List[Dict[str, Any]]:
        """Search GitHub repositories for a specific keyword.
        
        Args:
            client: HTTP client for API requests.
            keyword: Search keyword.
            
        Returns:
            List of repository data dictionaries.
        """
        await self.rate_limiter.acquire()
        
        # Build search query with filters
        query_parts = [
            keyword,
            f'stars:>={self.min_stars}',
            f'forks:>={self.min_forks}',
            'language:C OR language:C++ OR language:Python OR language:JavaScript',
            'NOT is:fork'  # Exclude forks to focus on original projects
        ]
        query = ' '.join(query_parts)
        
        headers = self._get_headers()
        params = {
            'q': query,
            'sort': 'stars',
            'order': 'desc',
            'per_page': min(self.max_results_per_query, 100),
            'page': 1
        }
        
        try:
            response = await client.get(
                f'{self.base_url}/search/repositories',
                headers=headers,
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            repositories = data.get('items', [])
            
            logger.debug(f"Found {len(repositories)} repositories for keyword: {keyword}")
            return repositories
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise RateLimitError("GitHub API rate limit exceeded")
            raise APIError(f"GitHub repository search failed: {e}")
        except Exception as e:
            raise APIError(f"GitHub repository search error: {e}")
    
    async def _extract_lead_from_repo(self, client: httpx.AsyncClient, repo: Dict[str, Any]) -> Optional[Lead]:
        """Extract lead information from repository data.
        
        Args:
            client: HTTP client for API requests.
            repo: Repository data from GitHub API.
            
        Returns:
            Lead object if valid company information found, None otherwise.
        """
        try:
            # Basic repository information
            repo_name = repo.get('name', '')
            full_name = repo.get('full_name', '')
            description = repo.get('description', '') or ''
            homepage = repo.get('homepage', '')
            
            # Owner information
            owner = repo.get('owner', {})
            owner_login = owner.get('login', '')
            owner_type = owner.get('type', '')
            
            # Skip individual users unless they have clear business indicators
            if owner_type == 'User' and not self._has_business_indicators(description, homepage):
                return None
            
            # Get README content for additional company information
            readme_content = await self._get_readme_content(client, full_name)
            
            # Extract company information
            company_info = self._extract_company_info(
                repo_name, description, homepage, readme_content
            )
            
            if not company_info['company_name']:
                return None
            
            # Calculate relevance score
            relevance_score = self._calculate_iot_relevance(description, readme_content)
            
            # Determine confidence level
            confidence = self._determine_confidence(repo, company_info, relevance_score)
            
            # Build lead object
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=LeadSourceType.GITHUB,
                source_id=full_name,
                source_url=HttpUrl(repo.get('html_url', '')),
                source_metadata={
                    'stars': repo.get('stargazers_count', 0),
                    'forks': repo.get('forks_count', 0),
                    'language': repo.get('language', ''),
                    'created_at': repo.get('created_at', ''),
                    'updated_at': repo.get('updated_at', ''),
                    'owner_type': owner_type,
                    'owner_login': owner_login
                },
                confidence_level=confidence,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"GitHub repository search"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error extracting lead from repository {repo.get('full_name', '')}: {e}")
            return None
    
    async def _extract_lead_from_org(self, client: httpx.AsyncClient, org_login: str) -> Optional[Lead]:
        """Extract lead information from GitHub organization.
        
        Args:
            client: HTTP client for API requests.
            org_login: Organization login name.
            
        Returns:
            Lead object if valid organization found, None otherwise.
        """
        try:
            await self.rate_limiter.acquire()
            
            headers = self._get_headers()
            response = await client.get(
                f'{self.base_url}/orgs/{org_login}',
                headers=headers
            )
            
            if response.status_code == 404:
                return None
            
            response.raise_for_status()
            org_data = response.json()
            
            # Extract organization information
            name = org_data.get('name') or org_login
            description = org_data.get('description', '') or ''
            blog = org_data.get('blog', '')
            email = org_data.get('email', '')
            location = org_data.get('location', '')
            
            # Skip if no meaningful company information
            if not self._has_business_indicators(description, blog):
                return None
            
            # Extract company information
            company_info = self._extract_company_info(name, description, blog, '')
            
            if not company_info['company_name']:
                return None
            
            # Add organization email if available
            if email and '@' in email:
                company_info['contact_emails'].append(email)
            
            # Calculate relevance score
            relevance_score = self._calculate_iot_relevance(description, '')
            
            # Organizations typically have higher confidence
            confidence = LeadConfidence.HIGH if relevance_score > 0.6 else LeadConfidence.MEDIUM
            
            # Build lead object
            lead = Lead(
                company_name=company_info['company_name'],
                company_url=company_info['company_url'],
                domain=company_info['domain'],
                description=company_info['description'],
                industry_tags=company_info['industry_tags'],
                technology_tags=company_info['technology_tags'],
                source_type=LeadSourceType.GITHUB,
                source_id=f"org:{org_login}",
                source_url=HttpUrl(org_data.get('html_url', '')),
                source_metadata={
                    'type': 'organization',
                    'public_repos': org_data.get('public_repos', 0),
                    'followers': org_data.get('followers', 0),
                    'following': org_data.get('following', 0),
                    'created_at': org_data.get('created_at', ''),
                    'location': location
                },
                confidence_level=confidence,
                relevance_score=relevance_score,
                contact_emails=company_info['contact_emails'],
                discovery_query=f"GitHub organization analysis"
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error extracting lead from organization {org_login}: {e}")
            return None
    
    async def _get_readme_content(self, client: httpx.AsyncClient, full_name: str) -> str:
        """Get README content from repository.
        
        Args:
            client: HTTP client for API requests.
            full_name: Repository full name (owner/repo).
            
        Returns:
            README content as string, empty if not found.
        """
        try:
            await self.rate_limiter.acquire()
            
            headers = self._get_headers()
            response = await client.get(
                f'{self.base_url}/repos/{full_name}/readme',
                headers=headers
            )
            
            if response.status_code == 404:
                return ''
            
            response.raise_for_status()
            readme_data = response.json()
            
            # GitHub API returns base64 encoded content
            import base64
            content = base64.b64decode(readme_data.get('content', '')).decode('utf-8', errors='ignore')
            
            # Limit content size to avoid processing huge READMEs
            return content[:10000]
            
        except Exception as e:
            logger.debug(f"Could not fetch README for {full_name}: {e}")
            return ''
    
    def _extract_company_info(self, name: str, description: str, homepage: str, 
                            readme_content: str) -> Dict[str, Any]:
        """Extract company information from various text sources.
        
        Args:
            name: Repository or organization name.
            description: Description text.
            homepage: Homepage URL.
            readme_content: README file content.
            
        Returns:
            Dictionary with extracted company information.
        """
        # Combine all text sources
        all_text = f"{name} {description} {readme_content}".lower()
        
        # Extract company name (prefer explicit mentions)
        company_name = self._extract_company_name(name, description, readme_content)
        
        # Extract and validate company URL
        company_url = None
        domain = None
        
        if homepage and validate_url(homepage):
            company_url = HttpUrl(homepage)
            domain = validate_domain(urlparse(homepage).netloc)
        else:
            # Look for URLs in text content
            url_match = re.search(r'https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', all_text)
            if url_match:
                found_url = url_match.group(0)
                if validate_url(found_url):
                    company_url = HttpUrl(found_url)
                    domain = validate_domain(urlparse(found_url).netloc)
        
        # Extract industry and technology tags
        industry_tags = self._extract_industry_tags(all_text)
        technology_tags = self._extract_technology_tags(all_text)
        
        # Extract contact emails
        contact_emails = self._extract_emails(all_text)
        
        # Create consolidated description
        consolidated_description = self._create_description(description, readme_content)
        
        return {
            'company_name': company_name,
            'company_url': company_url,
            'domain': domain,
            'description': consolidated_description,
            'industry_tags': industry_tags,
            'technology_tags': technology_tags,
            'contact_emails': contact_emails
        }
    
    def _extract_company_name(self, name: str, description: str, readme_content: str) -> str:
        """Extract company name from various sources.
        
        Args:
            name: Repository or organization name.
            description: Description text.
            readme_content: README content.
            
        Returns:
            Extracted company name or empty string.
        """
        # Check for explicit company mentions in description
        company_match = re.search(r'(?i)(?:by|from|@)\s+([A-Z][a-zA-Z\s&.-]{2,30})', description)
        if company_match:
            return company_match.group(1).strip()
        
        # Check for company patterns in README
        for pattern in self.company_patterns:
            match = re.search(pattern, readme_content)
            if match:
                # Extract surrounding context as potential company name
                start = max(0, match.start() - 50)
                end = min(len(readme_content), match.end() + 50)
                context = readme_content[start:end]
                
                # Look for capitalized words that could be company names
                name_match = re.search(r'([A-Z][a-zA-Z\s&.-]{2,30})', context)
                if name_match:
                    return name_match.group(1).strip()
        
        # Fallback to repository/org name if it looks like a company
        if self._has_business_indicators(name, ''):
            return name.replace('-', ' ').replace('_', ' ').title()
        
        return ''
    
    def _has_business_indicators(self, text: str, url: str) -> bool:
        """Check if text contains business indicators.
        
        Args:
            text: Text to analyze.
            url: Associated URL.
            
        Returns:
            True if business indicators found.
        """
        text_lower = text.lower()
        
        # Business keywords
        business_keywords = [
            'company', 'corp', 'corporation', 'inc', 'ltd', 'llc', 'gmbh',
            'technologies', 'solutions', 'systems', 'software', 'hardware',
            'startup', 'business', 'commercial', 'enterprise', 'professional'
        ]
        
        # Check for business keywords
        for keyword in business_keywords:
            if keyword in text_lower:
                return True
        
        # Check for company website
        if url and any(tld in url for tld in ['.com', '.io', '.tech', '.ai']):
            return True
        
        return False
    
    def _calculate_iot_relevance(self, description: str, readme_content: str) -> float:
        """Calculate IoT/embedded systems relevance score.
        
        Args:
            description: Repository description.
            readme_content: README content.
            
        Returns:
            Relevance score between 0.0 and 1.0.
        """
        text = f"{description} {readme_content}".lower()
        
        # Count keyword matches
        matches = 0
        total_keywords = len(self.iot_keywords)
        
        for keyword in self.iot_keywords:
            if keyword in text:
                matches += 1
        
        # Calculate base score
        base_score = matches / total_keywords
        
        # Boost score for high-value keywords
        high_value_keywords = ['iot', 'embedded', 'firmware', 'microcontroller', 'industrial iot']
        for keyword in high_value_keywords:
            if keyword in text:
                base_score += 0.1
        
        return min(base_score, 1.0)
    
    def _determine_confidence(self, repo: Dict[str, Any], company_info: Dict[str, Any], 
                           relevance_score: float) -> LeadConfidence:
        """Determine confidence level for a lead.
        
        Args:
            repo: Repository data.
            company_info: Extracted company information.
            relevance_score: IoT relevance score.
            
        Returns:
            Confidence level enumeration.
        """
        # Factors that increase confidence
        stars = repo.get('stargazers_count', 0)
        forks = repo.get('forks_count', 0)
        has_homepage = bool(company_info['company_url'])
        has_description = bool(company_info['description'])
        is_organization = repo.get('owner', {}).get('type') == 'Organization'
        
        confidence_score = 0
        
        # Repository popularity
        if stars >= 100:
            confidence_score += 2
        elif stars >= 20:
            confidence_score += 1
        
        if forks >= 20:
            confidence_score += 1
        
        # Company information completeness
        if has_homepage:
            confidence_score += 2
        if has_description:
            confidence_score += 1
        if is_organization:
            confidence_score += 2
        
        # IoT relevance
        if relevance_score >= 0.7:
            confidence_score += 2
        elif relevance_score >= 0.4:
            confidence_score += 1
        
        # Map score to confidence level
        if confidence_score >= 6:
            return LeadConfidence.HIGH
        elif confidence_score >= 3:
            return LeadConfidence.MEDIUM
        else:
            return LeadConfidence.LOW
    
    def _extract_industry_tags(self, text: str) -> List[str]:
        """Extract industry tags from text.
        
        Args:
            text: Text to analyze.
            
        Returns:
            List of industry tags.
        """
        industry_keywords = {
            'automotive': ['automotive', 'car', 'vehicle', 'transportation'],
            'healthcare': ['healthcare', 'medical', 'health', 'patient', 'hospital'],
            'industrial': ['industrial', 'manufacturing', 'factory', 'automation'],
            'smart_home': ['smart home', 'home automation', 'smart building'],
            'agriculture': ['agriculture', 'farming', 'crop', 'livestock', 'agtech'],
            'energy': ['energy', 'power', 'solar', 'wind', 'battery', 'grid'],
            'retail': ['retail', 'shopping', 'store', 'commerce', 'pos'],
            'logistics': ['logistics', 'shipping', 'supply chain', 'warehouse']
        }
        
        found_tags = []
        for tag, keywords in industry_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    found_tags.append(tag)
                    break
        
        return found_tags
    
    def _extract_technology_tags(self, text: str) -> List[str]:
        """Extract technology tags from text.
        
        Args:
            text: Text to analyze.
            
        Returns:
            List of technology tags.
        """
        tech_keywords = {
            'arduino': ['arduino'],
            'raspberry_pi': ['raspberry pi', 'rpi'],
            'esp32': ['esp32', 'esp8266'],
            'bluetooth': ['bluetooth', 'ble'],
            'wifi': ['wifi', 'wireless'],
            'mqtt': ['mqtt'],
            'python': ['python'],
            'c_cpp': ['c++', 'cpp', 'c programming'],
            'javascript': ['javascript', 'node.js', 'nodejs'],
            'cloud': ['aws', 'azure', 'gcp', 'cloud'],
            'mobile': ['android', 'ios', 'mobile app'],
            'web': ['web', 'html', 'css', 'react', 'vue']
        }
        
        found_tags = []
        for tag, keywords in tech_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    found_tags.append(tag)
                    break
        
        return found_tags
    
    def _extract_emails(self, text: str) -> List[str]:
        """Extract email addresses from text.
        
        Args:
            text: Text to analyze.
            
        Returns:
            List of valid email addresses.
        """
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        
        # Filter out common non-business emails
        filtered_emails = []
        from config.constants import EXCLUDED_DOMAINS
        exclude_domains = EXCLUDED_DOMAINS + ['github.com']
        
        for email in emails:
            domain = email.split('@')[1].lower()
            if domain not in exclude_domains:
                filtered_emails.append(email.lower())
        
        return list(set(filtered_emails))  # Remove duplicates
    
    def _create_description(self, description: str, readme_content: str) -> str:
        """Create consolidated description from multiple sources.
        
        Args:
            description: Repository description.
            readme_content: README content.
            
        Returns:
            Consolidated description.
        """
        if description:
            return description[:500]
        
        # Extract first meaningful paragraph from README
        if readme_content:
            lines = readme_content.split('\n')
            for line in lines:
                line = line.strip()
                if len(line) > 50 and not line.startswith('#'):
                    return line[:500]
        
        return ''
    
    def _deduplicate_leads(self, leads: List[Lead]) -> List[Lead]:
        """Remove duplicate leads based on domain and company name.
        
        Args:
            leads: List of leads to deduplicate.
            
        Returns:
            List of unique leads.
        """
        seen_domains = set()
        seen_names = set()
        unique_leads = []
        
        for lead in leads:
            # Create deduplication keys
            domain_key = lead.domain.lower() if lead.domain else ''
            name_key = lead.company_name.lower().strip()
            
            # Skip if we've seen this domain or very similar name
            if domain_key and domain_key in seen_domains:
                continue
            if name_key in seen_names:
                continue
            
            # Add to unique leads
            unique_leads.append(lead)
            
            if domain_key:
                seen_domains.add(domain_key)
            seen_names.add(name_key)
        
        return unique_leads
    
    def _score_leads(self, leads: List[Lead]) -> List[Lead]:
        """Score and sort leads by relevance and confidence.
        
        Args:
            leads: List of leads to score.
            
        Returns:
            List of scored and sorted leads.
        """
        # Sort by relevance score (descending) and confidence level
        confidence_order = {
            LeadConfidence.HIGH: 3,
            LeadConfidence.MEDIUM: 2,
            LeadConfidence.LOW: 1,
            LeadConfidence.UNKNOWN: 0
        }
        
        sorted_leads = sorted(
            leads,
            key=lambda x: (
                x.relevance_score or 0.0,
                confidence_order.get(x.confidence_level, 0)
            ),
            reverse=True
        )
        
        return sorted_leads
    
    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for GitHub API requests.
        
        Returns:
            Dictionary of HTTP headers.
        """
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'TatvixAI-ClientFinder/1.0'
        }
        
        if self.api_token:
            headers['Authorization'] = f'token {self.api_token}'
        
        return headers