"""Website validation utilities for Tatvix AI Client Discovery System.

This module provides comprehensive website validation including URL validation,
connectivity checks, and content verification to ensure only real, working
websites are added to the lead database.
"""

import asyncio
import aiohttp
import socket
import urllib.parse
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
import ssl
import certifi

from utils.logger import get_logger
from utils.exceptions import ValidationError


logger = get_logger(__name__)


class WebsiteValidator:
    """Comprehensive website validation and verification system."""
    
    def __init__(self, timeout: int = 10, max_retries: int = 2):
        """Initialize website validator.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = get_logger(__name__)
        
        # SSL context for secure connections
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())
        
    async def validate_website(self, url: str) -> Dict[str, Any]:
        """Comprehensive website validation.
        
        Args:
            url: Website URL to validate
            
        Returns:
            Dictionary containing validation results:
            {
                'is_valid': bool,
                'is_reachable': bool,
                'status_code': int,
                'response_time_ms': float,
                'final_url': str,
                'title': str,
                'error': str,
                'ssl_valid': bool,
                'domain_info': dict
            }
        """
        validation_start = datetime.utcnow()
        
        result = {
            'is_valid': False,
            'is_reachable': False,
            'status_code': None,
            'response_time_ms': None,
            'final_url': url,
            'title': '',
            'error': '',
            'ssl_valid': False,
            'domain_info': {},
            'validated_at': validation_start.isoformat()
        }
        
        try:
            # Step 1: URL format validation
            if not self._validate_url_format(url):
                result['error'] = 'Invalid URL format'
                return result
            
            # Step 2: Normalize URL
            normalized_url = self._normalize_url(url)
            result['final_url'] = normalized_url
            
            # Step 3: Domain validation
            domain_info = await self._validate_domain(normalized_url)
            result['domain_info'] = domain_info
            
            if not domain_info['is_valid']:
                result['error'] = f"Invalid domain: {domain_info['error']}"
                return result
            
            # Step 4: HTTP connectivity check
            connectivity_result = await self._check_connectivity(normalized_url)
            result.update(connectivity_result)
            
            if result['is_reachable']:
                result['is_valid'] = True
                self.logger.info(f"Website validation successful: {url} -> {result['status_code']}")
            else:
                self.logger.warning(f"Website not reachable: {url} - {result['error']}")
            
            return result
            
        except Exception as e:
            result['error'] = f"Validation error: {str(e)}"
            self.logger.error(f"Website validation failed for {url}: {e}")
            return result
    
    def _validate_url_format(self, url: str) -> bool:
        """Validate URL format and structure.
        
        Args:
            url: URL to validate
            
        Returns:
            True if URL format is valid
        """
        try:
            if not url or not isinstance(url, str):
                return False
            
            # Parse URL
            parsed = urllib.parse.urlparse(url)
            
            # Check required components
            if not parsed.netloc:
                return False
            
            # Check scheme
            if parsed.scheme not in ['http', 'https']:
                return False
            
            # Check domain format
            domain = parsed.netloc.lower()
            if not domain or '.' not in domain:
                return False
            
            # Check for valid characters
            if any(char in domain for char in [' ', '\t', '\n', '\r']):
                return False
            
            return True
            
        except Exception:
            return False
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL for consistent validation.
        
        Args:
            url: URL to normalize
            
        Returns:
            Normalized URL
        """
        url = url.strip()
        
        # Add scheme if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Parse and rebuild
        parsed = urllib.parse.urlparse(url)
        
        # Normalize domain
        domain = parsed.netloc.lower()
        
        # Remove www. prefix for consistency
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Rebuild URL
        normalized = urllib.parse.urlunparse((
            parsed.scheme,
            domain,
            parsed.path or '/',
            parsed.params,
            parsed.query,
            parsed.fragment
        ))
        
        return normalized
    
    async def _validate_domain(self, url: str) -> Dict[str, Any]:
        """Validate domain name and DNS resolution.
        
        Args:
            url: URL to validate domain for
            
        Returns:
            Domain validation results
        """
        domain_info = {
            'is_valid': False,
            'domain': '',
            'ip_address': '',
            'dns_resolvable': False,
            'error': ''
        }
        
        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc
            domain_info['domain'] = domain
            
            # DNS resolution check
            try:
                ip_address = socket.gethostbyname(domain)
                domain_info['ip_address'] = ip_address
                domain_info['dns_resolvable'] = True
                domain_info['is_valid'] = True
                
            except socket.gaierror as e:
                domain_info['error'] = f"DNS resolution failed: {e}"
                
        except Exception as e:
            domain_info['error'] = f"Domain validation error: {e}"
        
        return domain_info
    
    async def _check_connectivity(self, url: str) -> Dict[str, Any]:
        """Check HTTP connectivity and response.
        
        Args:
            url: URL to check connectivity for
            
        Returns:
            Connectivity check results
        """
        connectivity_result = {
            'is_reachable': False,
            'status_code': None,
            'response_time_ms': None,
            'title': '',
            'ssl_valid': False,
            'error': ''
        }
        
        start_time = datetime.utcnow()
        
        try:
            # Configure session with proper headers
            connector = aiohttp.TCPConnector(
                ssl=self.ssl_context,
                limit=10,
                limit_per_host=5,
                ttl_dns_cache=300,
                use_dns_cache=True
            )
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=headers
            ) as session:
                
                # Try HTTPS first, then HTTP
                for attempt_url in [url, url.replace('https://', 'http://')]:
                    try:
                        async with session.get(attempt_url, allow_redirects=True) as response:
                            end_time = datetime.utcnow()
                            response_time = (end_time - start_time).total_seconds() * 1000
                            
                            connectivity_result['status_code'] = response.status
                            connectivity_result['response_time_ms'] = response_time
                            connectivity_result['final_url'] = str(response.url)
                            
                            # Check if response is successful
                            if 200 <= response.status < 400:
                                connectivity_result['is_reachable'] = True
                                
                                # Check SSL if HTTPS
                                if attempt_url.startswith('https://'):
                                    connectivity_result['ssl_valid'] = True
                                
                                # Try to extract page title
                                try:
                                    if response.content_type and 'text/html' in response.content_type:
                                        content = await response.text()
                                        title = self._extract_title(content)
                                        connectivity_result['title'] = title
                                except Exception:
                                    pass  # Title extraction is optional
                                
                                return connectivity_result
                            
                            else:
                                connectivity_result['error'] = f"HTTP {response.status}: {response.reason}"
                                
                    except aiohttp.ClientError as e:
                        connectivity_result['error'] = f"Connection error: {str(e)}"
                        continue
                    
                    except asyncio.TimeoutError:
                        connectivity_result['error'] = f"Connection timeout after {self.timeout}s"
                        continue
                
        except Exception as e:
            connectivity_result['error'] = f"Connectivity check failed: {str(e)}"
        
        return connectivity_result
    
    def _extract_title(self, html_content: str) -> str:
        """Extract page title from HTML content.
        
        Args:
            html_content: HTML content to extract title from
            
        Returns:
            Page title or empty string
        """
        try:
            # Simple title extraction (could be enhanced with BeautifulSoup)
            import re
            
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
                # Clean up title
                title = re.sub(r'\s+', ' ', title)
                return title[:200]  # Limit length
            
        except Exception:
            pass
        
        return ''
    
    async def validate_multiple_websites(self, urls: List[str]) -> Dict[str, Dict[str, Any]]:
        """Validate multiple websites concurrently.
        
        Args:
            urls: List of URLs to validate
            
        Returns:
            Dictionary mapping URLs to validation results
        """
        if not urls:
            return {}
        
        self.logger.info(f"Validating {len(urls)} websites")
        
        # Create validation tasks
        tasks = []
        for url in urls:
            task = asyncio.create_task(self.validate_website(url))
            tasks.append((url, task))
        
        # Execute all validations concurrently
        results = {}
        for url, task in tasks:
            try:
                result = await task
                results[url] = result
            except Exception as e:
                results[url] = {
                    'is_valid': False,
                    'is_reachable': False,
                    'error': f"Validation task failed: {str(e)}"
                }
        
        # Log summary
        valid_count = sum(1 for result in results.values() if result['is_valid'])
        self.logger.info(f"Website validation completed: {valid_count}/{len(urls)} valid websites")
        
        return results


async def validate_website_url(url: str, timeout: int = 10) -> bool:
    """Quick website validation function.
    
    Args:
        url: URL to validate
        timeout: Request timeout in seconds
        
    Returns:
        True if website is valid and reachable
    """
    validator = WebsiteValidator(timeout=timeout)
    result = await validator.validate_website(url)
    return result['is_valid'] and result['is_reachable']


async def get_website_info(url: str, timeout: int = 10) -> Dict[str, Any]:
    """Get comprehensive website information.
    
    Args:
        url: URL to get information for
        timeout: Request timeout in seconds
        
    Returns:
        Website information dictionary
    """
    validator = WebsiteValidator(timeout=timeout)
    return await validator.validate_website(url)