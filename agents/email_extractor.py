"""Email Discovery & Verification System for Tatvix AI Client Discovery.

This module implements intelligent email discovery with verification capabilities,
ensuring high deliverability and compliance with anti-spam regulations.
"""

from __future__ import annotations

import asyncio
import re
import smtplib
import socket
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

import dns.resolver
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from config.settings import Settings
from utils.exceptions import ValidationError, ScrapingError
from utils.logger import get_logger
from utils.validators import validate_url

from .models import (
    EmailCandidate,
    EmailDiscoveryResult,
    EmailSourceType,
    EmailType,
    VerificationLevel,
    VerificationResult,
    VerificationStatus,
    QualityScore,
    ComplianceStatus,
    ComplianceFlag,
)
from .website_scraper import WebsiteScraper
from .rate_limiter import RateLimiter

logger = get_logger(__name__)


class EmailVerifier:
    """Email verification engine with DNS and optional SMTP checking."""
    
    def __init__(self, settings: Settings) -> None:
        """Initialize email verifier.
        
        Args:
            settings: Application settings configuration.
        """
        self._settings = settings
        self._log = logger
        self._timeout = settings.get_int('email', 'verification_timeout', fallback=10)
        self._smtp_enabled = settings.get_bool('email', 'smtp_verification_enabled', fallback=False)
        from agents.rate_limiter import RateLimitConfig
        rate_config = RateLimitConfig(
            requests_per_window=settings.get_int('email', 'verification_rate_limit', fallback=60),
            window_seconds=60
        )
        self._rate_limiter = RateLimiter(rate_config)
        
        # Load disposable domain list
        self._disposable_domains = self._load_disposable_domains()
        
        # Common role-based email prefixes
        self._role_based_prefixes = {
            'admin', 'administrator', 'contact', 'info', 'support', 'help',
            'sales', 'marketing', 'hr', 'noreply', 'no-reply', 'postmaster',
            'webmaster', 'abuse', 'security', 'privacy', 'legal', 'billing'
        }
    
    def _load_disposable_domains(self) -> Set[str]:
        """Load disposable email domain list.
        
        Returns:
            Set of disposable domain names.
        """
        # Basic disposable domain list - in production, this would be loaded from a file
        disposable_domains = {
            '10minutemail.com', 'guerrillamail.com', 'mailinator.com',
            'tempmail.org', 'yopmail.com', 'throwaway.email', 'temp-mail.org',
            'getnada.com', 'maildrop.cc', 'sharklasers.com'
        }
        return disposable_domains
    
    async def verify_email(self, email: str, level: VerificationLevel = VerificationLevel.DNS_MX) -> VerificationResult:
        """Verify email address at specified level.
        
        Args:
            email: Email address to verify.
            level: Verification level to perform.
            
        Returns:
            Verification result with detailed information.
        """
        start_time = time.time()
        
        try:
            # Rate limiting
            await self._rate_limiter.acquire()
            
            # Start with syntax validation
            syntax_valid = self._validate_syntax(email)
            if not syntax_valid:
                return VerificationResult(
                    email_address=email,
                    verification_level=VerificationLevel.SYNTAX_ONLY,
                    status=VerificationStatus.INVALID,
                    syntax_valid=False,
                    verification_duration_ms=(time.time() - start_time) * 1000,
                    error_message="Invalid email syntax"
                )
            
            # Extract domain
            domain = email.split('@')[1].lower()
            
            # Check if disposable domain
            is_disposable = domain in self._disposable_domains
            is_role_based = email.split('@')[0].lower() in self._role_based_prefixes
            
            result = VerificationResult(
                email_address=email,
                verification_level=level,
                status=VerificationStatus.VALID,
                syntax_valid=True,
                is_disposable_domain=is_disposable,
                is_role_based=is_role_based,
                verification_duration_ms=0  # Will be updated at the end
            )
            
            # DNS verification
            if level in [VerificationLevel.DNS_MX, VerificationLevel.SMTP_CONNECT, VerificationLevel.SMTP_RCPT, VerificationLevel.DELIVERABILITY]:
                await self._verify_dns(domain, result)
                
                if not result.mx_records_exist:
                    result.status = VerificationStatus.INVALID
                    result.verification_duration_ms = (time.time() - start_time) * 1000
                    return result
            
            # SMTP verification (if enabled and requested)
            if self._smtp_enabled and level in [VerificationLevel.SMTP_CONNECT, VerificationLevel.SMTP_RCPT]:
                await self._verify_smtp(email, result)
            
            # Deliverability assessment
            if level == VerificationLevel.DELIVERABILITY:
                await self._assess_deliverability(domain, result)
            
            # Set final duration
            result.verification_duration_ms = (time.time() - start_time) * 1000
            
            return result
            
        except Exception as e:
            self._log.error(f"Email verification failed for {email}: {e}")
            return VerificationResult(
                email_address=email,
                verification_level=level,
                status=VerificationStatus.ERROR,
                syntax_valid=syntax_valid if 'syntax_valid' in locals() else False,
                verification_duration_ms=(time.time() - start_time) * 1000,
                error_message=str(e)
            )
    
    def _validate_syntax(self, email: str) -> bool:
        """Validate email syntax according to RFC 5322.
        
        Args:
            email: Email address to validate.
            
        Returns:
            True if syntax is valid, False otherwise.
        """
        if not email or '@' not in email:
            return False
        
        # RFC 5322 compliant regex (simplified)
        pattern = re.compile(
            r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
        )
        
        if not pattern.match(email):
            return False
        
        # Additional length checks
        local, domain = email.split('@', 1)
        if len(local) > 64 or len(domain) > 253 or len(email) > 254:
            return False
        
        return True
    
    async def _verify_dns(self, domain: str, result: VerificationResult) -> None:
        """Verify domain DNS records.
        
        Args:
            domain: Domain to verify.
            result: Verification result to update.
        """
        try:
            # Check domain existence
            try:
                dns.resolver.resolve(domain, 'A')
                result.domain_exists = True
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                result.domain_exists = False
                result.mx_records_exist = False
                return
            except Exception:
                result.domain_exists = None
            
            # Check MX records
            try:
                mx_records = dns.resolver.resolve(domain, 'MX')
                result.mx_records_exist = True
                result.mx_records = [str(mx.exchange).rstrip('.') for mx in mx_records]
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                result.mx_records_exist = False
            except Exception as e:
                self._log.warning(f"MX lookup failed for {domain}: {e}")
                result.mx_records_exist = None
                
        except Exception as e:
            self._log.error(f"DNS verification failed for {domain}: {e}")
            result.domain_exists = None
            result.mx_records_exist = None
    
    async def _verify_smtp(self, email: str, result: VerificationResult) -> None:
        """Verify email via SMTP (if enabled).
        
        Args:
            email: Email address to verify.
            result: Verification result to update.
        """
        if not self._smtp_enabled:
            return
        
        domain = email.split('@')[1]
        if not result.mx_records:
            return
        
        # Try connecting to the first MX record
        mx_host = result.mx_records[0]
        
        try:
            # Create SMTP connection with timeout
            server = smtplib.SMTP(timeout=self._timeout)
            
            # Connect to MX server
            response_code, response_message = server.connect(mx_host, 25)
            result.smtp_connectable = response_code == 220
            result.smtp_response_code = response_code
            result.smtp_response_message = response_message.decode('utf-8', errors='ignore') if isinstance(response_message, bytes) else str(response_message)
            
            if result.smtp_connectable:
                # HELO/EHLO
                server.helo()
                
                # MAIL FROM (use a neutral sender)
                from config.constants import SMTP_TEST_EMAIL
                server.mail(SMTP_TEST_EMAIL)
                
                # RCPT TO (test the actual email)
                try:
                    code, message = server.rcpt(email)
                    result.smtp_accepts_mail = code in [250, 251]  # 250 = OK, 251 = User not local
                except smtplib.SMTPRecipientsRefused:
                    result.smtp_accepts_mail = False
                except Exception:
                    result.smtp_accepts_mail = None
            
            server.quit()
            
        except (socket.timeout, socket.error, smtplib.SMTPException) as e:
            self._log.debug(f"SMTP verification failed for {email}: {e}")
            result.smtp_connectable = False
            result.smtp_accepts_mail = None
        except Exception as e:
            self._log.error(f"Unexpected SMTP error for {email}: {e}")
            result.smtp_connectable = None
            result.smtp_accepts_mail = None
    
    async def _assess_deliverability(self, domain: str, result: VerificationResult) -> None:
        """Assess email deliverability indicators.
        
        Args:
            domain: Domain to assess.
            result: Verification result to update.
        """
        try:
            # Check SPF record
            try:
                txt_records = dns.resolver.resolve(domain, 'TXT')
                spf_found = any('v=spf1' in str(record) for record in txt_records)
                result.spf_record_exists = spf_found
            except Exception:
                result.spf_record_exists = False
            
            # Check DMARC record
            try:
                dmarc_domain = f'_dmarc.{domain}'
                txt_records = dns.resolver.resolve(dmarc_domain, 'TXT')
                dmarc_found = any('v=DMARC1' in str(record) for record in txt_records)
                result.dmarc_record_exists = dmarc_found
            except Exception:
                result.dmarc_record_exists = False
                
        except Exception as e:
            self._log.error(f"Deliverability assessment failed for {domain}: {e}")


class EmailExtractor:
    """Main email extraction and verification system."""
    
    def __init__(self, settings: Settings, website_scraper: Optional[WebsiteScraper] = None) -> None:
        """Initialize email extractor.
        
        Args:
            settings: Application settings configuration.
            website_scraper: Optional website scraper instance.
        """
        self._settings = settings
        self._log = logger
        self._website_scraper = website_scraper
        self._verifier = EmailVerifier(settings)
        
        # Configuration
        self._max_pages = settings.get_int('email', 'max_pages_per_domain', fallback=5)
        self._max_depth = settings.get_int('email', 'max_crawl_depth', fallback=2)
        self._timeout = settings.get_int('email', 'extraction_timeout', fallback=30)
        
        # Email extraction patterns
        self._email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
            re.IGNORECASE
        )
        
        self._obfuscated_patterns = [
            re.compile(r'\b([A-Za-z0-9._%+-]+)\s*\[?at\]?\s*([A-Za-z0-9.-]+)\s*\[?dot\]?\s*([A-Za-z]{2,})\b', re.IGNORECASE),
            re.compile(r'\b([A-Za-z0-9._%+-]+)\s*@\s*([A-Za-z0-9.-]+)\s*\.\s*([A-Za-z]{2,})\b', re.IGNORECASE),
        ]
        
        # Common email patterns for generation
        self._common_patterns = [
            'info', 'contact', 'hello', 'sales', 'support', 'admin',
            'marketing', 'business', 'office', 'team', 'mail'
        ]
    
    async def extract_emails_from_website(self, url: str, pre_fetched_html: Optional[str] = None) -> EmailDiscoveryResult:
        """Extract emails from website with multi-page discovery.
        
        Args:
            url: Base URL to extract emails from.
            pre_fetched_html: Optional pre-fetched HTML content.
            
        Returns:
            Complete email discovery result.
        """
        start_time = time.time()
        
        try:
            # Validate and normalize URL
            validated_url = validate_url(url)
            domain = urlparse(validated_url).netloc.lower()
            
            self._log.info(f"Starting email discovery for domain: {domain}")
            
            # Initialize result
            result = EmailDiscoveryResult(
                domain=domain,
                base_url=HttpUrl(validated_url),
                discovery_duration_seconds=0
            )
            
            # Collect URLs to crawl
            urls_to_crawl = await self._collect_crawl_urls(validated_url, pre_fetched_html)
            result.pages_crawled = urls_to_crawl
            
            # Extract emails from all pages
            all_candidates = []
            for page_url in urls_to_crawl:
                try:
                    candidates = await self._extract_emails_from_page(page_url)
                    all_candidates.extend(candidates)
                except Exception as e:
                    self._log.warning(f"Failed to extract emails from {page_url}: {e}")
            
            # Deduplicate candidates
            unique_candidates = self._deduplicate_candidates(all_candidates)
            
            # Generate additional email patterns
            generated_patterns = self.generate_email_patterns(domain, self._extract_names_from_candidates(unique_candidates))
            result.generated_patterns = generated_patterns
            
            # Create candidates from generated patterns
            for pattern in generated_patterns:
                candidate = EmailCandidate(
                    email_address=pattern,
                    source_type=EmailSourceType.PATTERN_GENERATION,
                    source_page_url=HttpUrl(validated_url),
                    confidence_score=0.7
                )
                unique_candidates.append(candidate)
            
            # Final deduplication
            result.email_candidates = self._deduplicate_candidates(unique_candidates)
            result.total_candidates_found = len(result.email_candidates)
            
            # Set success status
            result.success = True
            result.discovery_duration_seconds = time.time() - start_time
            
            self._log.info(f"Email discovery completed for {domain}: {len(result.email_candidates)} candidates found")
            
            return result
            
        except Exception as e:
            self._log.error(f"Email discovery failed for {url}: {e}")
            return EmailDiscoveryResult(
                domain=urlparse(url).netloc.lower(),
                base_url=HttpUrl(url),
                success=False,
                error_message=str(e),
                discovery_duration_seconds=time.time() - start_time
            )
    
    async def _collect_crawl_urls(self, base_url: str, pre_fetched_html: Optional[str] = None) -> List[str]:
        """Collect URLs to crawl for email discovery.
        
        Args:
            base_url: Base URL to start crawling from.
            pre_fetched_html: Optional pre-fetched HTML content.
            
        Returns:
            List of URLs to crawl.
        """
        urls_to_crawl = [base_url]
        parsed_base = urlparse(base_url)
        
        try:
            # If we have pre-fetched HTML, use it for the base page
            if pre_fetched_html:
                soup = BeautifulSoup(pre_fetched_html, 'html.parser')
            elif self._website_scraper:
                # Use website scraper to get content
                company_data = await self._website_scraper.scrape_website(base_url)
                if company_data.success and hasattr(company_data, 'html_content'):
                    soup = BeautifulSoup(getattr(company_data, 'html_content', ''), 'html.parser')
                else:
                    return urls_to_crawl
            else:
                return urls_to_crawl
            
            # Find contact-related pages
            contact_keywords = ['contact', 'about', 'team', 'staff', 'people', 'leadership']
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                
                # Convert relative URLs to absolute
                if href.startswith('/'):
                    full_url = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
                elif href.startswith('http'):
                    full_url = href
                else:
                    full_url = urljoin(base_url, href)
                
                # Check if it's a same-origin URL
                parsed_url = urlparse(full_url)
                if parsed_url.netloc != parsed_base.netloc:
                    continue
                
                # Check if it's a contact-related page
                url_text = (href + ' ' + link.get_text()).lower()
                if any(keyword in url_text for keyword in contact_keywords):
                    if full_url not in urls_to_crawl and len(urls_to_crawl) < self._max_pages:
                        urls_to_crawl.append(full_url)
            
        except Exception as e:
            self._log.warning(f"Failed to collect crawl URLs from {base_url}: {e}")
        
        return urls_to_crawl[:self._max_pages]
    
    async def _extract_emails_from_page(self, url: str) -> List[EmailCandidate]:
        """Extract email candidates from a single page.
        
        Args:
            url: URL to extract emails from.
            
        Returns:
            List of email candidates found on the page.
        """
        candidates = []
        
        try:
            if not self._website_scraper:
                return candidates
            
            # Scrape the page
            company_data = await self._website_scraper.scrape_website(url)
            if not company_data.success:
                return candidates
            
            # Get HTML content (assuming website_scraper stores it)
            html_content = getattr(company_data, 'html_content', '')
            if not html_content:
                return candidates
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract direct email addresses
            candidates.extend(self._extract_direct_emails(soup, url))
            
            # Extract mailto links
            candidates.extend(self._extract_mailto_links(soup, url))
            
            # Extract obfuscated emails
            candidates.extend(self._extract_obfuscated_emails(soup, url))
            
        except Exception as e:
            self._log.error(f"Failed to extract emails from {url}: {e}")
        
        return candidates
    
    def _extract_direct_emails(self, soup: BeautifulSoup, source_url: str) -> List[EmailCandidate]:
        """Extract direct email addresses from HTML.
        
        Args:
            soup: BeautifulSoup parsed HTML.
            source_url: Source page URL.
            
        Returns:
            List of email candidates.
        """
        candidates = []
        text_content = soup.get_text()
        
        # Find all email matches
        for match in self._email_pattern.finditer(text_content):
            email = match.group().lower()
            
            # Get surrounding context
            start = max(0, match.start() - 50)
            end = min(len(text_content), match.end() + 50)
            context = text_content[start:end].strip()
            
            # Determine source type based on context and URL
            source_type = self._determine_source_type(source_url, context)
            
            candidate = EmailCandidate(
                email_address=email,
                source_type=source_type,
                source_page_url=HttpUrl(source_url),
                source_context=context,
                confidence_score=0.9
            )
            
            candidates.append(candidate)
        
        return candidates
    
    def _extract_mailto_links(self, soup: BeautifulSoup, source_url: str) -> List[EmailCandidate]:
        """Extract emails from mailto links.
        
        Args:
            soup: BeautifulSoup parsed HTML.
            source_url: Source page URL.
            
        Returns:
            List of email candidates.
        """
        candidates = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('mailto:'):
                email = href[7:].split('?')[0].lower()  # Remove mailto: and query params
                
                if self._email_pattern.match(email):
                    context = link.get_text() or link.get('title', '')
                    
                    candidate = EmailCandidate(
                        email_address=email,
                        source_type=EmailSourceType.MAILTO_LINK,
                        source_page_url=HttpUrl(source_url),
                        source_context=context,
                        confidence_score=0.95
                    )
                    
                    candidates.append(candidate)
        
        return candidates
    
    def _extract_obfuscated_emails(self, soup: BeautifulSoup, source_url: str) -> List[EmailCandidate]:
        """Extract obfuscated email addresses.
        
        Args:
            soup: BeautifulSoup parsed HTML.
            source_url: Source page URL.
            
        Returns:
            List of email candidates.
        """
        candidates = []
        text_content = soup.get_text()
        
        for pattern in self._obfuscated_patterns:
            for match in pattern.finditer(text_content):
                try:
                    if len(match.groups()) == 3:
                        local, domain, tld = match.groups()
                        email = f"{local}@{domain}.{tld}".lower()
                    else:
                        continue
                    
                    if self._email_pattern.match(email):
                        context = match.group()
                        
                        candidate = EmailCandidate(
                            email_address=email,
                            source_type=EmailSourceType.DIRECT_EXTRACTION,
                            source_page_url=HttpUrl(source_url),
                            source_context=context,
                            is_obfuscated=True,
                            confidence_score=0.8
                        )
                        
                        candidates.append(candidate)
                        
                except Exception as e:
                    self._log.debug(f"Failed to process obfuscated email match: {e}")
        
        return candidates
    
    def _determine_source_type(self, url: str, context: str) -> EmailSourceType:
        """Determine email source type based on URL and context.
        
        Args:
            url: Source page URL.
            context: Surrounding text context.
            
        Returns:
            Email source type.
        """
        url_lower = url.lower()
        context_lower = context.lower()
        
        if 'contact' in url_lower or 'contact' in context_lower:
            return EmailSourceType.CONTACT_PAGE
        elif any(keyword in url_lower for keyword in ['team', 'about', 'staff', 'people']):
            return EmailSourceType.TEAM_PAGE
        elif any(keyword in context_lower for keyword in ['footer', 'copyright', '©']):
            return EmailSourceType.FOOTER_EXTRACTION
        else:
            return EmailSourceType.DIRECT_EXTRACTION
    
    def _extract_names_from_candidates(self, candidates: List[EmailCandidate]) -> List[str]:
        """Extract potential names from email candidates for pattern generation.
        
        Args:
            candidates: List of email candidates.
            
        Returns:
            List of extracted names.
        """
        names = []
        
        for candidate in candidates:
            email_local = candidate.email_address.split('@')[0]
            
            # Skip role-based emails
            if email_local in self._common_patterns:
                continue
            
            # Extract potential names from email local part
            if '.' in email_local:
                parts = email_local.split('.')
                names.extend(parts)
            elif '_' in email_local:
                parts = email_local.split('_')
                names.extend(parts)
            else:
                names.append(email_local)
        
        # Filter and clean names
        cleaned_names = []
        for name in names:
            if len(name) >= 2 and name.isalpha():
                cleaned_names.append(name.lower())
        
        return list(set(cleaned_names))
    
    def _deduplicate_candidates(self, candidates: List[EmailCandidate]) -> List[EmailCandidate]:
        """Remove duplicate email candidates.
        
        Args:
            candidates: List of email candidates.
            
        Returns:
            Deduplicated list of candidates.
        """
        seen_emails = set()
        unique_candidates = []
        
        for candidate in candidates:
            if candidate.email_address not in seen_emails:
                seen_emails.add(candidate.email_address)
                unique_candidates.append(candidate)
        
        return unique_candidates
    
    def generate_email_patterns(self, domain: str, names: List[str]) -> List[str]:
        """Generate common email patterns for a domain.
        
        Args:
            domain: Domain to generate patterns for.
            names: List of names found on the website.
            
        Returns:
            List of generated email patterns.
        """
        patterns = []
        
        # Common role-based patterns
        for pattern in self._common_patterns:
            email = f"{pattern}@{domain}"
            patterns.append(email)
        
        # Name-based patterns (if names were found)
        for name in names[:5]:  # Limit to first 5 names
            patterns.extend([
                f"{name}@{domain}",
                f"{name[0]}.{name}@{domain}" if len(name) > 1 else f"{name}@{domain}",
            ])
        
        # Remove duplicates and return
        return list(set(patterns))
    
    async def verify_email_deliverability(self, email: str, level: VerificationLevel = VerificationLevel.DNS_MX) -> VerificationResult:
        """Verify email deliverability at specified level.
        
        Args:
            email: Email address to verify.
            level: Verification level to perform.
            
        Returns:
            Verification result.
        """
        return await self._verifier.verify_email(email, level)
    
    def assess_email_quality(self, email: str, domain_info: Optional[Dict[str, Any]] = None) -> QualityScore:
        """Assess email quality and engagement potential.
        
        Args:
            email: Email address to assess.
            domain_info: Optional domain information for assessment.
            
        Returns:
            Quality score assessment.
        """
        domain = email.split('@')[1].lower()
        local_part = email.split('@')[0].lower()
        
        # Initialize scores
        deliverability_score = 0.5
        engagement_score = 0.5
        reputation_score = 0.5
        authenticity_score = 0.5
        
        quality_factors = {}
        risk_factors = []
        positive_signals = []
        
        # Assess based on email characteristics
        if local_part in self._common_patterns:
            engagement_score = 0.3  # Role-based emails have lower engagement
            risk_factors.append("role_based_email")
        else:
            engagement_score = 0.7
            positive_signals.append("personal_email")
        
        # Domain reputation (basic assessment)
        if domain in self._verifier._disposable_domains:
            deliverability_score = 0.1
            reputation_score = 0.1
            risk_factors.append("disposable_domain")
        else:
            positive_signals.append("permanent_domain")
        
        # Length and complexity assessment
        if len(local_part) < 3:
            authenticity_score = 0.3
            risk_factors.append("very_short_local_part")
        elif len(local_part) > 20:
            authenticity_score = 0.4
            risk_factors.append("very_long_local_part")
        else:
            authenticity_score = 0.8
            positive_signals.append("reasonable_length")
        
        # Special character assessment
        special_chars = set(local_part) - set('abcdefghijklmnopqrstuvwxyz0123456789._-')
        if special_chars:
            authenticity_score *= 0.8
            risk_factors.append("special_characters")
        
        # Calculate overall quality
        weights = {
            'deliverability': 0.3,
            'engagement': 0.3,
            'reputation': 0.25,
            'authenticity': 0.15
        }
        
        overall_quality = (
            deliverability_score * weights['deliverability'] +
            engagement_score * weights['engagement'] +
            reputation_score * weights['reputation'] +
            authenticity_score * weights['authenticity']
        )
        
        # Determine risk level
        if overall_quality >= 0.8:
            risk_level = 'low'
        elif overall_quality >= 0.6:
            risk_level = 'medium'
        elif overall_quality >= 0.4:
            risk_level = 'high'
        else:
            risk_level = 'critical'
        
        quality_factors = {
            'deliverability': deliverability_score,
            'engagement': engagement_score,
            'reputation': reputation_score,
            'authenticity': authenticity_score
        }
        
        return QualityScore(
            email_address=email,
            deliverability_score=deliverability_score,
            engagement_score=engagement_score,
            reputation_score=reputation_score,
            authenticity_score=authenticity_score,
            overall_quality=overall_quality,
            risk_level=risk_level,
            quality_factors=quality_factors,
            risk_factors=risk_factors,
            positive_signals=positive_signals
        )
    
    def check_compliance_status(self, domain: str, page_content: Optional[str] = None) -> ComplianceStatus:
        """Check GDPR and CAN-SPAM compliance indicators.
        
        Args:
            domain: Domain to check compliance for.
            page_content: Optional page content for analysis.
            
        Returns:
            Compliance status assessment.
        """
        compliance_flags = []
        compliance_notes = []
        gdpr_indicators = []
        can_spam_indicators = []
        
        if page_content:
            content_lower = page_content.lower()
            
            # Check for privacy policy
            if any(term in content_lower for term in ['privacy policy', 'privacy notice', 'data protection']):
                compliance_flags.append(ComplianceFlag.PRIVACY_POLICY_PRESENT)
                gdpr_indicators.append("Privacy policy referenced")
            
            # Check for contact information
            if any(term in content_lower for term in ['contact us', 'contact information', 'address']):
                compliance_flags.append(ComplianceFlag.CONTACT_INFO_PUBLIC)
                can_spam_indicators.append("Contact information available")
            
            # Check for unsubscribe mechanism
            if any(term in content_lower for term in ['unsubscribe', 'opt-out', 'opt out']):
                compliance_flags.append(ComplianceFlag.UNSUBSCRIBE_MECHANISM)
                can_spam_indicators.append("Unsubscribe mechanism present")
            
            # Check for data processing notices
            if any(term in content_lower for term in ['gdpr', 'data processing', 'legal basis']):
                compliance_flags.append(ComplianceFlag.DATA_PROCESSING_NOTICE)
                gdpr_indicators.append("Data processing notice found")
            
            # Check for cookie consent
            if any(term in content_lower for term in ['cookie', 'cookies', 'consent']):
                compliance_flags.append(ComplianceFlag.COOKIE_CONSENT)
                gdpr_indicators.append("Cookie consent mechanism")
            
            # Check for terms of service
            if any(term in content_lower for term in ['terms of service', 'terms and conditions', 'legal terms']):
                compliance_flags.append(ComplianceFlag.TERMS_OF_SERVICE)
                compliance_notes.append("Terms of service available")
        
        # Calculate compliance score
        max_flags = len(ComplianceFlag)
        compliance_score = len(compliance_flags) / max_flags
        
        # Add compliance notes
        compliance_notes.extend([
            "Compliance assessment is indicative only",
            "Legal review required for marketing activities",
            "Phase 1 is for discovery only - no bulk email sending"
        ])
        
        return ComplianceStatus(
            domain=domain,
            compliance_flags=compliance_flags,
            gdpr_compliant_indicators=gdpr_indicators,
            can_spam_indicators=can_spam_indicators,
            compliance_score=compliance_score,
            compliance_notes=compliance_notes
        )