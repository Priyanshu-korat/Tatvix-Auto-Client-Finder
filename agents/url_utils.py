"""URL utilities for search result processing.

This module provides URL validation, normalization, and domain extraction
utilities for consistent URL handling across the search pipeline.
"""

import re
import logging
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse, urljoin
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
import socket

from utils.logger import get_logger


logger = get_logger(__name__)


def normalize_domain(url: str) -> Optional[str]:
    """Normalize domain from URL for consistent processing.
    
    Args:
        url: URL string to extract and normalize domain from.
        
    Returns:
        Normalized domain string or None if invalid.
    """
    return URLUtilities.extract_domain(url)


class URLUtilities:
    """URL processing utilities for search results."""
    
    # Domain validation regex
    DOMAIN_REGEX = re.compile(
        r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$'
    )
    
    # Common subdomains to remove during normalization
    COMMON_SUBDOMAINS = {'www', 'web', 'site', 'home', 'main'}
    
    # Invalid/blocked domains
    @classmethod
    def _get_blocked_domains(cls):
        """Get blocked domains including configured exclusions."""
        from config.constants import EXCLUDED_DOMAINS
        base_blocked = {
            'facebook.com', 'twitter.com', 'linkedin.com', 'youtube.com',
            'google.com', 'bing.com', 'yahoo.com', 'duckduckgo.com'
        }
        return base_blocked.union(set(EXCLUDED_DOMAINS))
    
    @classmethod
    def normalize_url(cls, url: str) -> Optional[str]:
        """Normalize URL for consistent processing.
        
        Args:
            url: Raw URL string to normalize.
            
        Returns:
            Normalized URL string or None if invalid.
        """
        if not url or not isinstance(url, str):
            logger.warning(f"Invalid URL input: {url}")
            return None
        
        try:
            # Clean and prepare URL
            url = url.strip().lower()
            
            # Add protocol if missing
            if not url.startswith(('http://', 'https://')):
                url = f'https://{url}'
            
            # Parse URL components
            parsed = urlparse(url)
            
            if not parsed.netloc:
                logger.warning(f"No domain found in URL: {url}")
                return None
            
            # Normalize domain
            normalized_domain = cls._normalize_domain(parsed.netloc)
            if not normalized_domain:
                return None
            
            # Reconstruct normalized URL
            normalized_parsed = parsed._replace(
                scheme='https',
                netloc=normalized_domain,
                path=parsed.path.rstrip('/') or '/',
                query='',
                fragment=''
            )
            
            normalized_url = urlunparse(normalized_parsed)
            
            logger.debug(f"Normalized URL: {url} -> {normalized_url}")
            return normalized_url
            
        except Exception as e:
            logger.error(f"URL normalization failed for {url}: {e}")
            return None
    
    @classmethod
    def extract_domain(cls, url: str) -> Optional[str]:
        """Extract and normalize domain from URL.
        
        Args:
            url: URL string to extract domain from.
            
        Returns:
            Normalized domain string or None if invalid.
        """
        if not url or not isinstance(url, str):
            return None
        
        try:
            # Handle URLs without protocol
            if not url.startswith(('http://', 'https://')):
                url = f'https://{url}'
            
            parsed = urlparse(url)
            if not parsed.netloc:
                return None
            
            return cls._normalize_domain(parsed.netloc)
            
        except Exception as e:
            logger.error(f"Domain extraction failed for {url}: {e}")
            return None
    
    @classmethod
    def _normalize_domain(cls, domain: str) -> Optional[str]:
        """Normalize domain string.
        
        Args:
            domain: Raw domain string.
            
        Returns:
            Normalized domain or None if invalid.
        """
        if not domain:
            return None
        
        try:
            # Remove port number
            domain = domain.split(':')[0].lower().strip()
            
            # Remove common subdomains
            parts = domain.split('.')
            if len(parts) > 2 and parts[0] in cls.COMMON_SUBDOMAINS:
                domain = '.'.join(parts[1:])
            
            # Validate domain format
            if not cls.DOMAIN_REGEX.match(domain):
                logger.warning(f"Invalid domain format: {domain}")
                return None
            
            # Check against blocked domains
            if domain in cls.BLOCKED_DOMAINS:
                logger.info(f"Blocked domain filtered: {domain}")
                return None
            
            return domain
            
        except Exception as e:
            logger.error(f"Domain normalization failed for {domain}: {e}")
            return None
    
    @classmethod
    def validate_url(cls, url: str) -> Tuple[bool, Optional[str]]:
        """Validate URL accessibility and format.
        
        Args:
            url: URL to validate.
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        if not url or not isinstance(url, str):
            return False, "Invalid URL format"
        
        try:
            # Basic URL structure validation
            parsed = urlparse(url)
            if not parsed.netloc or not parsed.scheme:
                return False, "Missing domain or protocol"
            
            # Domain validation
            domain = cls.extract_domain(url)
            if not domain:
                return False, "Invalid domain"
            
            # Check if domain is blocked
            if domain in cls.BLOCKED_DOMAINS:
                return False, f"Blocked domain: {domain}"
            
            return True, None
            
        except Exception as e:
            return False, f"URL validation error: {str(e)}"
    
    @classmethod
    def check_url_accessibility(cls, url: str, timeout: int = 10) -> Tuple[bool, Optional[str]]:
        """Check if URL is accessible via HTTP request.
        
        Args:
            url: URL to check.
            timeout: Request timeout in seconds.
            
        Returns:
            Tuple of (is_accessible, error_message).
        """
        try:
            # Validate URL format first
            is_valid, error_msg = cls.validate_url(url)
            if not is_valid:
                return False, error_msg
            
            # Attempt HTTP request
            with urlopen(url, timeout=timeout) as response:
                status_code = response.getcode()
                if 200 <= status_code < 400:
                    return True, None
                else:
                    return False, f"HTTP {status_code}"
                    
        except HTTPError as e:
            return False, f"HTTP error: {e.code}"
        except URLError as e:
            return False, f"URL error: {e.reason}"
        except socket.timeout:
            return False, "Request timeout"
        except Exception as e:
            return False, f"Accessibility check failed: {str(e)}"
    
    @classmethod
    def get_root_domain(cls, domain: str) -> Optional[str]:
        """Extract root domain from subdomain.
        
        Args:
            domain: Domain string (may include subdomains).
            
        Returns:
            Root domain or None if invalid.
        """
        if not domain:
            return None
        
        try:
            # Simple root domain extraction
            parts = domain.split('.')
            if len(parts) < 2:
                return None
            
            # Handle common TLD patterns
            if len(parts) >= 3 and parts[-2] in {'co', 'com', 'net', 'org', 'gov', 'edu'}:
                return '.'.join(parts[-3:])
            else:
                return '.'.join(parts[-2:])
                
        except Exception as e:
            logger.error(f"Root domain extraction failed for {domain}: {e}")
            return None
    
    @classmethod
    def are_same_domain(cls, url1: str, url2: str) -> bool:
        """Check if two URLs belong to the same domain.
        
        Args:
            url1: First URL.
            url2: Second URL.
            
        Returns:
            True if same domain, False otherwise.
        """
        domain1 = cls.extract_domain(url1)
        domain2 = cls.extract_domain(url2)
        
        if not domain1 or not domain2:
            return False
        
        # Compare root domains
        root1 = cls.get_root_domain(domain1)
        root2 = cls.get_root_domain(domain2)
        
        return root1 == root2 if root1 and root2 else domain1 == domain2
    
    @classmethod
    def clean_search_url(cls, url: str) -> Optional[str]:
        """Clean URL from search engine redirects and tracking.
        
        Args:
            url: Raw URL from search results.
            
        Returns:
            Cleaned URL or None if invalid.
        """
        if not url:
            return None
        
        try:
            # Handle Google redirect URLs
            if 'google.com/url?' in url:
                parsed = urlparse(url)
                if parsed.query:
                    from urllib.parse import parse_qs
                    params = parse_qs(parsed.query)
                    if 'url' in params:
                        url = params['url'][0]
                    elif 'q' in params:
                        url = params['q'][0]
            
            # Handle other common redirects
            redirect_patterns = [
                r'redirect\.php\?.*?url=([^&]+)',
                r'out\.php\?.*?url=([^&]+)',
                r'link\.php\?.*?url=([^&]+)'
            ]
            
            for pattern in redirect_patterns:
                match = re.search(pattern, url, re.IGNORECASE)
                if match:
                    from urllib.parse import unquote
                    url = unquote(match.group(1))
                    break
            
            # Normalize the cleaned URL
            return cls.normalize_url(url)
            
        except Exception as e:
            logger.error(f"URL cleaning failed for {url}: {e}")
            return cls.normalize_url(url)  # Fallback to basic normalization