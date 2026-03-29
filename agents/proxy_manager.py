"""Rotating proxy configuration for Playwright-based scraping."""

from __future__ import annotations

import itertools
import threading
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import unquote, urlparse

from config.settings import Settings


class ProxyManager:
    """Thread-safe round-robin proxy selection for browser contexts.

    Proxies are read from settings (comma-separated URLs). Each URL may include
    credentials in the form ``http://user:pass@host:port``.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize proxy manager from application settings.

        Args:
            settings: Singleton settings instance.
        """
        self._settings = settings
        raw = settings.get('scraping', 'proxy_urls', fallback='').strip()
        self._proxies: List[str] = [
            p.strip() for p in raw.split(',') if p.strip()
        ]
        self._lock = threading.Lock()
        self._index_cycle: Iterator[int] = (
            itertools.cycle(range(len(self._proxies))) if self._proxies else iter(())
        )

    def has_proxies(self) -> bool:
        """Return True if at least one proxy URL is configured."""
        return len(self._proxies) > 0

    def get_playwright_proxy(self) -> Optional[Dict[str, Any]]:
        """Return the next proxy as a Playwright proxy dict, or None if unset.

        Returns:
            Dictionary with ``server`` and optional ``username`` / ``password``,
            or None when no proxies are configured.
        """
        if not self._proxies:
            return None
        with self._lock:
            idx = next(self._index_cycle)
            url = self._proxies[idx]
        return self._parse_proxy_url(url)

    @staticmethod
    def _parse_proxy_url(url: str) -> Dict[str, Any]:
        """Parse a proxy URL into Playwright proxy options.

        Args:
            url: HTTP or HTTPS proxy URL, optionally with userinfo.

        Returns:
            Playwright-compatible proxy mapping.

        Raises:
            ValueError: If the URL scheme or host is missing.
        """
        parsed = urlparse(url.strip())
        if parsed.scheme not in ('http', 'https'):
            raise ValueError(f"Unsupported proxy scheme for URL: {url!r}")
        host = parsed.hostname
        if not host:
            raise ValueError(f"Proxy URL missing host: {url!r}")
        port = parsed.port
        server = f"{parsed.scheme}://{host}"
        if port:
            server = f"{server}:{port}"
        result: Dict[str, Any] = {'server': server}
        if parsed.username:
            result['username'] = unquote(parsed.username)
        if parsed.password:
            result['password'] = unquote(parsed.password)
        return result
