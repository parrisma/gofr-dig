"""HTTP fetcher with anti-detection support.

This module provides async HTTP fetching with configurable anti-detection
headers and rate limiting.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlparse

import aiohttp

from app.logger import session_logger as logger
from app.scraping.antidetection import AntiDetectionManager
from app.scraping.state import get_scraping_state


@dataclass
class FetchResult:
    """Result of an HTTP fetch operation.

    Attributes:
        url: The URL that was fetched
        status_code: HTTP status code
        content: Response body as string
        content_type: Content-Type header value
        headers: Response headers
        encoding: Character encoding used
        error: Error message if fetch failed
    """

    url: str
    status_code: int
    content: str
    content_type: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    encoding: str = "utf-8"
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if the fetch was successful."""
        return self.error is None and 200 <= self.status_code < 400


class HTTPFetcher:
    """Async HTTP fetcher with anti-detection support.

    This fetcher uses the global scraping state to determine anti-detection
    settings and rate limiting.

    Example:
        fetcher = HTTPFetcher()
        result = await fetcher.fetch("https://example.com")
        if result.success:
            print(result.content)
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_redirects: int = 10,
    ):
        """Initialize the HTTP fetcher.

        Args:
            timeout: Request timeout in seconds
            max_redirects: Maximum number of redirects to follow
        """
        self.timeout = timeout
        self.max_redirects = max_redirects
        self._last_request_time: Dict[str, float] = {}  # domain -> timestamp

    def _get_manager(self) -> AntiDetectionManager:
        """Get an AntiDetectionManager configured from global state."""
        state = get_scraping_state()
        return AntiDetectionManager(
            profile=state.antidetection_profile,
            custom_headers=state.custom_headers,
            custom_user_agent=state.custom_user_agent,
        )

    async def _rate_limit(self, url: str) -> None:
        """Apply rate limiting based on domain.

        Args:
            url: The URL being fetched
        """
        state = get_scraping_state()
        delay = state.rate_limit_delay

        if delay <= 0:
            return

        parsed = urlparse(url)
        domain = parsed.netloc

        now = asyncio.get_event_loop().time()
        last_time = self._last_request_time.get(domain, 0)
        elapsed = now - last_time

        if elapsed < delay:
            wait_time = delay - elapsed
            logger.debug("Rate limiting", domain=domain, wait_seconds=wait_time)
            await asyncio.sleep(wait_time)

        self._last_request_time[domain] = asyncio.get_event_loop().time()

    async def fetch(
        self,
        url: str,
        rotate_user_agent: bool = False,
        additional_headers: Optional[Dict[str, str]] = None,
    ) -> FetchResult:
        """Fetch a URL with anti-detection headers.

        Args:
            url: The URL to fetch
            rotate_user_agent: If True, rotate to a new User-Agent
            additional_headers: Extra headers to include in the request

        Returns:
            FetchResult with the response data or error
        """
        # Validate URL
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return FetchResult(
                url=url,
                status_code=0,
                content="",
                error=f"Invalid URL scheme: {parsed.scheme}. Only http and https are supported.",
            )

        # Apply rate limiting
        await self._rate_limit(url)

        # Get headers from anti-detection manager
        manager = self._get_manager()
        headers = manager.get_headers(rotate_user_agent)

        # Add any additional headers
        if additional_headers:
            headers.update(additional_headers)

        logger.debug("Fetching URL", url=url, headers=list(headers.keys()))

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            connector = aiohttp.TCPConnector(
                limit=10,
                enable_cleanup_closed=True,
            )

            async with aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
            ) as session:
                async with session.get(
                    url,
                    headers=headers,
                    max_redirects=self.max_redirects,
                    allow_redirects=True,
                ) as response:
                    # Detect encoding
                    encoding = response.charset or "utf-8"

                    # Read content
                    content = await response.text(encoding=encoding)

                    # Get content type
                    content_type = response.headers.get("Content-Type")

                    # Convert headers to dict
                    response_headers = dict(response.headers)

                    logger.info(
                        "Fetch completed",
                        url=url,
                        status=response.status,
                        content_length=len(content),
                    )

                    return FetchResult(
                        url=str(response.url),  # Final URL after redirects
                        status_code=response.status,
                        content=content,
                        content_type=content_type,
                        headers=response_headers,
                        encoding=encoding,
                    )

        except aiohttp.ClientError as e:
            logger.error("Fetch failed", url=url, error=str(e))
            return FetchResult(
                url=url,
                status_code=0,
                content="",
                error=f"HTTP error: {str(e)}",
            )
        except asyncio.TimeoutError:
            logger.error("Fetch timeout", url=url, timeout=self.timeout)
            return FetchResult(
                url=url,
                status_code=0,
                content="",
                error=f"Request timed out after {self.timeout} seconds",
            )
        except Exception as e:
            logger.error("Unexpected fetch error", url=url, error=str(e))
            return FetchResult(
                url=url,
                status_code=0,
                content="",
                error=f"Unexpected error: {str(e)}",
            )


# Global fetcher instance
_fetcher: Optional[HTTPFetcher] = None


def get_fetcher() -> HTTPFetcher:
    """Get the global HTTP fetcher instance.

    Returns:
        HTTPFetcher: The global fetcher
    """
    global _fetcher
    if _fetcher is None:
        _fetcher = HTTPFetcher()
    return _fetcher


async def fetch_url(
    url: str,
    rotate_user_agent: bool = False,
    additional_headers: Optional[Dict[str, str]] = None,
) -> FetchResult:
    """Convenience function to fetch a URL.

    Args:
        url: The URL to fetch
        rotate_user_agent: If True, rotate to a new User-Agent
        additional_headers: Extra headers to include

    Returns:
        FetchResult with the response data or error
    """
    fetcher = get_fetcher()
    return await fetcher.fetch(url, rotate_user_agent, additional_headers)
