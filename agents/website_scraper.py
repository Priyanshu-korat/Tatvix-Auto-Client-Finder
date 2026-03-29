"""Playwright-based website scraper with BeautifulSoup extraction."""

from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from bs4 import BeautifulSoup
from pydantic import HttpUrl

from config.constants import IOT_KEYWORDS
from config.settings import Settings
from utils.exceptions import ScrapingError, ValidationError
from utils.logger import get_logger
from utils.validators import validate_url

from .models import BusinessType, CompanyData, CompanySize
from .proxy_manager import ProxyManager

logger = get_logger(__name__)

try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        Playwright,
        TimeoutError as PlaywrightTimeoutError,
    )
except ImportError:
    async_playwright = None  # type: ignore[assignment,misc]
    Browser = None  # type: ignore[assignment,misc]
    Playwright = None  # type: ignore[assignment,misc]
    PlaywrightTimeoutError = Exception  # type: ignore[assignment,misc]

_DEFAULT_USER_AGENTS: Tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
)

_TECH_PATTERN = re.compile(
    r"\b(python|javascript|typescript|node\.?js|react|vue|angular|django|flask|fastapi|"
    r"aws|azure|gcp|kubernetes|docker|terraform|mqtt|coap|zigbee|lora|bluetooth|wifi|"
    r"arduino|raspberry\s*pi|embedded\s*c|c\+\+|\.net|java|spring|postgresql|mongodb|"
    r"redis|elasticsearch|graphql|rest\s*api|aws\s*iot|azure\s*iot)\b",
    re.IGNORECASE,
)

_PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{2,5})?"
)

_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)


def _sanitize_plain_text(value: str, max_len: int) -> str:
    """Remove null bytes and control characters; cap length."""
    if not value:
        return ""
    cleaned = value.replace("\x00", "")
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    return cleaned


def _strip_scripts(soup: BeautifulSoup) -> None:
    """Remove executable and non-content nodes before text extraction."""
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()


class WebsiteScraper:
    """Headless Playwright scraper with structured company extraction."""

    def __init__(self, settings: Settings, proxy_manager: ProxyManager) -> None:
        """Create a scraper instance.

        Args:
            settings: Application settings.
            proxy_manager: Proxy rotation helper (may have zero proxies configured).
        """
        self._settings = settings
        self._proxy_manager = proxy_manager
        self._log = logger
        self._timeout_ms = int(settings.get_float("scraping", "timeout", fallback=30.0) * 1000)
        self._max_page_size = settings.get_int("scraping", "max_page_size", fallback=10485760)
        self._delay_min = settings.get_float("scraping", "delay_min", fallback=2.0)
        self._delay_max = settings.get_float("scraping", "delay_max", fallback=5.0)
        if self._delay_min > self._delay_max:
            self._delay_min, self._delay_max = self._delay_max, self._delay_min
        self._max_retries = max(1, settings.get_int("scraping", "max_retries", fallback=3))
        self._retry_backoff_base = settings.get_float("scraping", "retry_backoff_base", fallback=2.0)
        self._max_concurrent = settings.get_int("scraping", "max_concurrent", fallback=3)
        self._headless = settings.get_bool("scraping", "playwright_headless", fallback=True)
        self._enabled = settings.get_bool("scraping", "enabled", fallback=True)
        self._semaphore = asyncio.Semaphore(max(1, self._max_concurrent))
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._browser_lock = asyncio.Lock()

    def _user_agent_pool(self) -> List[str]:
        """Build rotating user-agent list from settings and defaults."""
        desktop = self._settings.get("scraping", "user_agent_desktop", fallback="").strip()
        mobile = self._settings.get("scraping", "user_agent_mobile", fallback="").strip()
        pool: List[str] = []
        for agent in (desktop, mobile):
            if agent and agent not in pool:
                pool.append(agent)
        for agent in _DEFAULT_USER_AGENTS:
            if agent not in pool:
                pool.append(agent)
        return pool

    def _pick_user_agent(self) -> str:
        """Return a random user agent from the pool."""
        pool = self._user_agent_pool()
        return random.choice(pool)

    async def _ensure_browser(self) -> Browser:
        """Lazily start Playwright and launch a shared Chromium instance."""
        if async_playwright is None:
            raise ScrapingError(
                "Playwright is not installed. Add playwright to dependencies and run "
                "'playwright install chromium'.",
            )
        async with self._browser_lock:
            if self._browser is not None:
                return self._browser
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._log.info(
                "Playwright Chromium browser started",
                extra={"extra_fields": {"component": "website_scraper"}},
            )
            return self._browser

    async def close(self) -> None:
        """Close the shared browser and stop Playwright."""
        async with self._browser_lock:
            if self._browser is not None:
                await self._browser.close()
                self._browser = None
            if self._pw is not None:
                await self._pw.stop()
                self._pw = None
            self._log.info(
                "Playwright browser stopped",
                extra={"extra_fields": {"component": "website_scraper"}},
            )

    async def __aenter__(self) -> "WebsiteScraper":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def scrape_website(self, url: str) -> CompanyData:
        """Navigate to URL and return structured ``CompanyData``.

        Args:
            url: HTTP or HTTPS URL to scrape.

        Returns:
            Validated ``CompanyData`` instance.

        Raises:
            ValidationError: If URL is invalid or scraping is disabled.
            ScrapingError: If navigation fails after retries.
        """
        if not self._enabled:
            raise ValidationError(
                "Web scraping is disabled via configuration",
                field_name="scraping.enabled",
                validation_rule="feature_disabled",
            )
        normalized = validate_url(url, field_name="url")
        started = time.perf_counter()
        async with self._semaphore:
            await self._pre_request_delay()
            html: Optional[str] = None
            status: Optional[int] = None
            last_error: Optional[str] = None
            for attempt in range(self._max_retries):
                try:
                    html, status = await self._fetch_html(normalized)
                    break
                except ScrapingError as exc:
                    last_error = str(exc.message)
                    self._log.warning(
                        "Scrape attempt failed",
                        extra={
                            "extra_fields": {
                                "component": "website_scraper",
                                "url": normalized,
                                "attempt": attempt + 1,
                                "max_retries": self._max_retries,
                                "error": last_error,
                            }
                        },
                    )
                    if attempt + 1 >= self._max_retries:
                        raise
                    backoff = self._retry_backoff_base ** attempt + random.uniform(0, 0.5)
                    await asyncio.sleep(backoff)
                    await self._pre_request_delay()
            if html is None:
                raise ScrapingError(
                    f"Failed to retrieve page: {last_error}",
                    url=normalized,
                )
            raw_bytes = html.encode("utf-8", errors="ignore")
            if len(raw_bytes) > self._max_page_size:
                self._log.warning(
                    "Page exceeded max size; truncating for parsing",
                    extra={
                        "extra_fields": {
                            "component": "website_scraper",
                            "url": normalized,
                            "max_page_size": self._max_page_size,
                        }
                    },
                )
                html = raw_bytes[: self._max_page_size].decode("utf-8", errors="ignore")
        duration = time.perf_counter() - started
        company_info = await self.extract_company_info(html)
        contacts_emails, contacts_phones, contact_hints = await self._split_contacts(
            await self.extract_contact_info(html)
        )
        tech = self.detect_technology_stack(html)
        text_for_classify = _sanitize_plain_text(
            f"{company_info.get('description') or ''} {company_info.get('raw_text_sample') or ''}",
            8000,
        )
        business_type = self.classify_business_type(text_for_classify)
        size_hint = self._classify_company_size(text_for_classify)
        industry_hints = self._industry_hints_from_text(text_for_classify)
        product_cues = self._product_service_cues(text_for_classify)
        page_title = company_info.get("page_title")
        description = company_info.get("description")
        company_name = company_info.get("company_name")
        data = CompanyData(
            url=HttpUrl(normalized),
            success=True,
            http_status=status,
            page_title=page_title,
            company_name=company_name,
            description=description,
            industry_hints=industry_hints,
            contact_emails=contacts_emails,
            contact_phones=contacts_phones,
            contact_hints=contact_hints,
            technology_signals=tech,
            product_service_cues=product_cues,
            business_type=business_type,
            company_size_hint=size_hint,
            scraped_at=datetime.utcnow(),
            scrape_duration_seconds=round(duration, 3),
        )
        self._log.info(
            "Scrape completed",
            extra={
                "extra_fields": {
                    "component": "website_scraper",
                    "url": normalized,
                    "duration_seconds": round(duration, 3),
                    "http_status": status,
                    "business_type": business_type.value,
                }
            },
        )
        return data

    async def _pre_request_delay(self) -> None:
        """Random delay between requests (anti-detection)."""
        delay = random.uniform(self._delay_min, self._delay_max)
        await asyncio.sleep(delay)

    async def _fetch_html(self, url: str) -> Tuple[str, Optional[int]]:
        """Load document HTML with Playwright."""
        browser = await self._ensure_browser()
        user_agent = self._pick_user_agent()
        proxy = self._proxy_manager.get_playwright_proxy()
        context_kwargs: Dict[str, Any] = {
            "user_agent": user_agent,
            "viewport": {"width": 1280, "height": 720},
            "java_script_enabled": True,
        }
        if proxy:
            context_kwargs["proxy"] = proxy
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()
        page.set_default_timeout(self._timeout_ms)
        try:
            response = await page.goto(url, wait_until="domcontentloaded")
            status = response.status if response else None
            if status is not None and status >= 400:
                raise ScrapingError(
                    f"HTTP error status {status}",
                    url=url,
                    http_status=status,
                )
            html = await page.content()
            return html, status
        except PlaywrightTimeoutError:
            raise ScrapingError(
                "Navigation timed out",
                url=url,
                timeout=True,
            )
        except ScrapingError:
            raise
        except Exception as exc:
            raise ScrapingError(
                f"Navigation failed: {exc}",
                url=url,
            )
        finally:
            await context.close()

    async def extract_company_info(self, page_content: str) -> Dict[str, Any]:
        """Parse company name, title, and description from HTML.

        Args:
            page_content: Raw HTML string.

        Returns:
            Dictionary with optional ``company_name``, ``page_title``, ``description``,
            and ``raw_text_sample`` for classification.
        """
        if not page_content or not page_content.strip():
            return {}
        soup = BeautifulSoup(page_content, "lxml")
        _strip_scripts(soup)
        title_tag = soup.find("title")
        page_title = _sanitize_plain_text(title_tag.get_text(strip=True), 500) if title_tag else None
        og_title = soup.find("meta", property="og:title")
        og_title_val = (
            _sanitize_plain_text(og_title.get("content", "").strip(), 500)
            if og_title and og_title.get("content")
            else None
        )
        meta_desc = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        if not meta_desc:
            meta_desc = soup.find("meta", property="og:description")
        description: Optional[str] = None
        if meta_desc and meta_desc.get("content"):
            description = _sanitize_plain_text(meta_desc["content"].strip(), 2000)
        h1 = soup.find("h1")
        h1_text = _sanitize_plain_text(h1.get_text(strip=True), 200) if h1 else None
        company_name = og_title_val or h1_text or page_title
        body = soup.find("body")
        raw_text = ""
        if body:
            raw_text = _sanitize_plain_text(body.get_text(separator=" ", strip=True), 8000)
        if not description and raw_text:
            description = _sanitize_plain_text(raw_text[:600], 2000)
        return {
            "company_name": company_name,
            "page_title": og_title_val or page_title,
            "description": description,
            "raw_text_sample": raw_text[:4000] if raw_text else None,
        }

    async def extract_contact_info(self, page_content: str) -> List[str]:
        """Extract email and phone-like strings from HTML.

        Args:
            page_content: Raw HTML string.

        Returns:
            List of sanitized contact strings (emails and phone numbers).
        """
        if not page_content or not page_content.strip():
            return []
        soup = BeautifulSoup(page_content, "lxml")
        _strip_scripts(soup)
        text = soup.get_text(separator=" ", strip=True)
        text = _sanitize_plain_text(text, 500000)
        emails = _EMAIL_PATTERN.findall(text)
        phones = [m.group(0) for m in _PHONE_PATTERN.finditer(text) if len(m.group(0)) >= 8]
        seen: Set[str] = set()
        out: List[str] = []
        for item in emails + phones:
            s = item.strip()
            if not s or s in seen:
                continue
            if "<" in s or ">" in s:
                continue
            seen.add(s)
            out.append(s[:320])
            if len(out) >= 80:
                break
        return out

    async def _split_contacts(self, contacts: List[str]) -> Tuple[List[str], List[str], List[str]]:
        """Split flat contact strings into emails, phones, and other hints."""
        emails: List[str] = []
        phones: List[str] = []
        hints: List[str] = []
        for raw in contacts:
            c = raw.strip().rstrip('.,;)]}"\'')
            if "@" in c and _EMAIL_PATTERN.fullmatch(c):
                if c not in emails:
                    emails.append(c)
            elif re.search(r"\d", c) and len(c) >= 8:
                if c not in phones:
                    phones.append(c)
            else:
                if c not in hints:
                    hints.append(c)
        return emails, phones, hints

    def detect_technology_stack(self, page_content: str) -> List[str]:
        """Detect technology keywords in HTML or visible text.

        Args:
            page_content: Raw HTML string.

        Returns:
            Lowercase deduplicated technology signal strings.
        """
        if not page_content:
            return []
        soup = BeautifulSoup(page_content, "lxml")
        _strip_scripts(soup)
        blob = soup.get_text(separator=" ", strip=True).lower()
        for meta in soup.find_all("meta", attrs={"name": re.compile(r"generator", re.I)}):
            if meta.get("content"):
                blob += " " + meta["content"].lower()
        found: Set[str] = set()
        for m in _TECH_PATTERN.finditer(blob):
            found.add(m.group(1).lower().replace(" ", " "))
        return sorted(found)[:50]

    def classify_business_type(self, content: str) -> BusinessType:
        """Heuristic business type from visible text (pre-AI).

        Args:
            content: Plain text or condensed page text.

        Returns:
            ``BusinessType`` enum value.
        """
        if not content:
            return BusinessType.UNKNOWN
        text = content.lower()
        enterprise_signals = (
            "fortune 500",
            "global enterprise",
            "multinational",
            "enterprise solutions",
            "listed on",
            "nasdaq",
            "nyse",
        )
        startup_signals = (
            "seed round",
            "series a",
            "series b",
            "y combinator",
            "accelerator",
            "early-stage",
            "early stage",
            "founders",
            "startup",
        )
        sme_signals = (
            "sme",
            "mid-market",
            "midmarket",
            "small business",
            "family-owned",
            "50-200 employees",
            "51-200",
        )
        if any(s in text for s in enterprise_signals):
            return BusinessType.ENTERPRISE
        if any(s in text for s in startup_signals):
            return BusinessType.STARTUP
        if any(s in text for s in sme_signals):
            return BusinessType.SME
        return BusinessType.UNKNOWN

    def _classify_company_size(self, content: str) -> CompanySize:
        """Infer company size bucket from textual cues."""
        if not content:
            return CompanySize.UNKNOWN
        text = content.lower()
        if re.search(r"\b(500\+|1000\+|10\s*000\+|employees?:\s*[5-9]\d{2,})\b", text):
            return CompanySize.LARGE
        if re.search(r"\b(51-200|201-500|employees?:\s*[5-9]\d)\b", text):
            return CompanySize.MEDIUM
        if re.search(r"\b(11-50|employees?:\s*1?\d)\b", text):
            return CompanySize.SMALL
        if re.search(r"\b(1-10|2-10|founding team|two founders|three founders)\b", text):
            return CompanySize.STARTUP
        return CompanySize.UNKNOWN

    def _industry_hints_from_text(self, content: str) -> List[str]:
        """Collect simple industry keywords based on IoT / embedded lexicon."""
        if not content:
            return []
        text = content.lower()
        hints: List[str] = []
        for kw in IOT_KEYWORDS:
            if kw.lower() in text and kw not in hints:
                hints.append(kw)
            if len(hints) >= 30:
                break
        return hints

    def _product_service_cues(self, content: str) -> List[str]:
        """Short phrases suggesting products or services."""
        if not content:
            return []
        cues: List[str] = []
        pattern = (
            r"\b(iot platform|embedded software|firmware development|hardware design|"
            r"custom pcb|industrial automation|smart device|edge analytics)\b"
        )
        text = content.lower()
        for m in re.finditer(pattern, text, re.IGNORECASE):
            phrase = m.group(1).strip().lower()
            if phrase not in cues:
                cues.append(phrase)
        return cues[:30]
