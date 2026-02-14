"""HTTP fetcher with anti-detection support.

This module provides async HTTP fetching with configurable anti-detection
headers, rate limiting, and retry logic with exponential backoff.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlparse

import aiohttp

from app.logger import session_logger as logger
from app.scraping.antidetection import AntiDetectionManager, AntiDetectionProfile
from app.scraping.state import get_scraping_state
from app.scraping.url_validator import validate_url

# Optional curl_cffi import for browser TLS fingerprinting
try:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    CurlAsyncSession = None  # type: ignore[assignment, misc]


# Retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 30.0  # seconds
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}  # Status codes that trigger retry


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
        retry_count: Number of retries performed
        rate_limited: True if rate limited (429) was encountered
    """

    url: str
    status_code: int
    content: str
    content_type: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    encoding: str = "utf-8"
    error: Optional[str] = None
    retry_count: int = 0
    rate_limited: bool = False

    @property
    def success(self) -> bool:
        """Check if the fetch was successful."""
        return self.error is None and 200 <= self.status_code < 400


class HTTPFetcher:
    """Async HTTP fetcher with anti-detection support and retry logic.

    This fetcher uses the global scraping state to determine anti-detection
    settings and rate limiting. Includes exponential backoff for retries
    and respects Retry-After headers for 429 responses.

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
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
    ):
        """Initialize the HTTP fetcher.

        Args:
            timeout: Request timeout in seconds
            max_redirects: Maximum number of redirects to follow
            max_retries: Maximum number of retry attempts for transient failures
            base_delay: Base delay for exponential backoff (seconds)
            max_delay: Maximum delay between retries (seconds)
        """
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._last_request_time: Dict[str, float] = {}  # domain -> timestamp

    def _get_manager(self) -> AntiDetectionManager:
        """Get an AntiDetectionManager configured from global state."""
        state = get_scraping_state()
        return AntiDetectionManager(
            profile=state.antidetection_profile,
            custom_headers=state.custom_headers,
            custom_user_agent=state.custom_user_agent,
        )

    def _calculate_backoff(self, attempt: int, retry_after: Optional[int] = None) -> float:
        """Calculate backoff delay for retry.

        Uses exponential backoff with jitter. If a Retry-After header is provided,
        uses that value instead.

        Args:
            attempt: Current retry attempt (0-indexed)
            retry_after: Optional Retry-After header value in seconds

        Returns:
            Delay in seconds before next retry
        """
        if retry_after is not None:
            # Respect server's Retry-After header, with a cap
            return min(retry_after, self.max_delay)

        # Exponential backoff with jitter: base * 2^attempt + random jitter
        delay = self.base_delay * (2 ** attempt)
        jitter = random.uniform(0, self.base_delay)
        return min(delay + jitter, self.max_delay)

    def _parse_retry_after(self, headers: Dict[str, str]) -> Optional[int]:
        """Parse Retry-After header value.

        Args:
            headers: Response headers

        Returns:
            Retry delay in seconds, or None if not present/parseable
        """
        retry_after = headers.get("Retry-After")
        if retry_after is None:
            return None

        try:
            # Try parsing as integer (seconds)
            return int(retry_after)
        except ValueError:
            # Could be HTTP-date format, but we'll just use default backoff
            logger.debug("Could not parse Retry-After header", value=retry_after)
            return None

    def _should_retry(self, status_code: int, attempt: int) -> bool:
        """Determine if a request should be retried.

        Args:
            status_code: HTTP status code from response
            attempt: Current attempt number (0-indexed)

        Returns:
            True if request should be retried
        """
        if attempt >= self.max_retries:
            return False
        return status_code in RETRY_STATUS_CODES

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

    async def _fetch_with_curl_cffi(
        self,
        url: str,
        additional_headers: Optional[Dict[str, str]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> FetchResult:
        """Fetch using curl_cffi with browser TLS fingerprint impersonation.

        This method bypasses TLS fingerprinting detection used by sites like Wikipedia.

        Args:
            url: The URL to fetch
            additional_headers: Extra headers to include in the request
            timeout_seconds: Optional timeout override for this request

        Returns:
            FetchResult with the response data or error
        """
        if not CURL_CFFI_AVAILABLE or CurlAsyncSession is None:
            return FetchResult(
                url=url,
                status_code=0,
                content="",
                error="curl_cffi is not installed. Install with: uv pip install curl_cffi",
            )

        attempt = 0
        rate_limited = False
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout
        fetch_start = time.perf_counter()
        url_host = urlparse(url).netloc

        while True:
            try:
                async with CurlAsyncSession(impersonate="chrome") as session:
                    # Prepare headers
                    headers = additional_headers.copy() if additional_headers else {}

                    logger.debug(
                        "Fetching URL with curl_cffi",
                        url=url,
                        impersonate="chrome",
                    )

                    response = await session.get(
                        url,
                        headers=headers,
                        timeout=effective_timeout,
                        allow_redirects=True,
                        max_redirects=self.max_redirects,
                    )

                    # Check if we should retry
                    if self._should_retry(response.status_code, attempt):
                        response_headers = dict(response.headers)
                        retry_after = self._parse_retry_after(response_headers)
                        backoff = self._calculate_backoff(attempt, retry_after)

                        if response.status_code == 429:
                            rate_limited = True
                            logger.warning(
                                f"fetch.retry {url_host} HTTP 429 rate-limited "
                                f"(attempt {attempt + 1}/{self.max_retries}, "
                                f"backoff {backoff:.1f}s). "
                                f"Remediation: reduce request rate or wait for retry window",
                                event="fetch_retry",
                                operation="fetch_url",
                                stage="fetch",
                                dependency="target_site",
                                cause_type="HTTP429",
                                impact="request_delayed_retrying",
                                remediation="respect_retry_after_or_reduce_request_rate",
                                url=url,
                                attempt=attempt + 1,
                                retry_after=retry_after,
                                backoff=backoff,
                            )
                        else:
                            logger.warning(
                                f"fetch.retry {url_host} HTTP {response.status_code} server error "
                                f"(attempt {attempt + 1}/{self.max_retries}, "
                                f"backoff {backoff:.1f}s). "
                                f"Remediation: check target site health or try later",
                                event="fetch_retry",
                                operation="fetch_url",
                                stage="fetch",
                                dependency="target_site",
                                cause_type="HTTPServerError",
                                impact="request_delayed_retrying",
                                remediation="retry_with_backoff_or_validate_target_availability",
                                url=url,
                                status=response.status_code,
                                attempt=attempt + 1,
                                backoff=backoff,
                            )

                        await asyncio.sleep(backoff)
                        attempt += 1
                        continue

                    # Get content
                    content = response.text
                    content_type = response.headers.get("Content-Type")
                    response_headers = dict(response.headers)

                    # Detect encoding from response or default to utf-8
                    encoding = response.encoding or "utf-8"

                    # Set error for HTTP error status codes
                    error_msg = None
                    if response.status_code >= 400:
                        error_msg = f"HTTP {response.status_code}"

                    duration_ms = int((time.perf_counter() - fetch_start) * 1000)
                    logger.info(
                        f"fetch.done {url_host} HTTP {response.status_code} "
                        f"{len(content):,} bytes {duration_ms}ms"
                        + (f" (retries={attempt})" if attempt else ""),
                        url=url,
                        status=response.status_code,
                        content_length=len(content),
                        duration_ms=duration_ms,
                        retries=attempt,
                        backend="curl_cffi",
                    )

                    return FetchResult(
                        url=str(response.url),
                        status_code=response.status_code,
                        content=content,
                        content_type=content_type,
                        headers=response_headers,
                        encoding=encoding,
                        error=error_msg,
                        retry_count=attempt,
                        rate_limited=rate_limited,
                    )

            except asyncio.TimeoutError as e:
                last_error = str(e) or "Request timed out"
                if attempt < self.max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(
                        f"fetch.timeout {url_host} timed out after {effective_timeout}s "
                        f"(attempt {attempt + 1}/{self.max_retries}, "
                        f"backoff {backoff:.1f}s). "
                        f"Remediation: increase timeout_seconds or check if site is slow/down",
                        event="fetch_retry",
                        operation="fetch_url",
                        stage="fetch",
                        dependency="target_site",
                        cause_type="TimeoutError",
                        impact="request_delayed_retrying",
                        remediation="retry_with_higher_timeout_or_validate_target_availability",
                        url=url,
                        error=last_error,
                        timeout_seconds=effective_timeout,
                        attempt=attempt + 1,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    attempt += 1
                    continue
                else:
                    duration_ms = int((time.perf_counter() - fetch_start) * 1000)
                    logger.error(
                        f"fetch.failed {url_host} timed out after {attempt + 1} attempts "
                        f"({duration_ms}ms total). "
                        f"Remediation: verify target is reachable, increase timeout, "
                        f"or check network between container and target",
                        event="fetch_failed",
                        operation="fetch_url",
                        stage="fetch",
                        dependency="target_site",
                        cause_type="TimeoutError",
                        impact="request_failed",
                        remediation="validate_target_availability_or_increase_timeout",
                        url=url,
                        error=last_error,
                        duration_ms=duration_ms,
                        attempts=attempt + 1,
                    )
                    return FetchResult(
                        url=url,
                        status_code=0,
                        content="",
                        error=f"HTTP error after {attempt + 1} attempts: {last_error}",
                        retry_count=attempt,
                        rate_limited=rate_limited,
                    )

            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(
                        f"fetch.error {url_host} {type(e).__name__}: {last_error[:120]} "
                        f"(attempt {attempt + 1}/{self.max_retries}, "
                        f"backoff {backoff:.1f}s). "
                        f"Remediation: check DNS, connectivity, or antidetection profile",
                        event="fetch_retry",
                        operation="fetch_url",
                        stage="fetch",
                        dependency="target_site",
                        cause_type=type(e).__name__,
                        impact="request_delayed_retrying",
                        remediation="retry_with_backoff_or_check_dns_connectivity",
                        url=url,
                        error=last_error,
                        attempt=attempt + 1,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    attempt += 1
                    continue
                else:
                    duration_ms = int((time.perf_counter() - fetch_start) * 1000)
                    logger.error(
                        f"fetch.failed {url_host} {type(e).__name__} after {attempt + 1} "
                        f"attempts ({duration_ms}ms total): {last_error[:200]}. "
                        f"Remediation: check target connectivity, DNS resolution, "
                        f"or try a different antidetection profile",
                        event="fetch_failed",
                        operation="fetch_url",
                        stage="fetch",
                        dependency="target_site",
                        cause_type=type(e).__name__,
                        impact="request_failed",
                        remediation="check_target_connectivity_or_review_antidetection_profile",
                        url=url,
                        error=last_error,
                        duration_ms=duration_ms,
                        attempts=attempt + 1,
                    )
                    return FetchResult(
                        url=url,
                        status_code=0,
                        content="",
                        error=f"HTTP error after {attempt + 1} attempts: {last_error}",
                        retry_count=attempt,
                        rate_limited=rate_limited,
                    )

    async def fetch(
        self,
        url: str,
        rotate_user_agent: bool = False,
        additional_headers: Optional[Dict[str, str]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> FetchResult:
        """Fetch a URL with anti-detection headers and retry logic.

        Implements exponential backoff with jitter for transient failures.
        Respects Retry-After headers for 429 responses.

        Args:
            url: The URL to fetch
            rotate_user_agent: If True, rotate to a new User-Agent
            additional_headers: Extra headers to include in the request
            timeout_seconds: Optional timeout override for this request

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

        # SSRF protection: block private/internal IPs
        is_safe, reason = validate_url(url)
        if not is_safe:
            return FetchResult(
                url=url,
                status_code=0,
                content="",
                error=reason,
            )

        # Apply rate limiting
        await self._rate_limit(url)

        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout

        # Check if BROWSER_TLS profile is active - use curl_cffi
        state = get_scraping_state()
        if state.antidetection_profile == AntiDetectionProfile.BROWSER_TLS:
            return await self._fetch_with_curl_cffi(url, additional_headers, effective_timeout)

        # Get headers from anti-detection manager
        manager = self._get_manager()
        headers = manager.get_headers(rotate_user_agent)

        # Add any additional headers
        if additional_headers:
            headers.update(additional_headers)

        logger.debug("Fetching URL", url=url, headers=list(headers.keys()))

        attempt = 0
        last_error: Optional[str] = None
        rate_limited = False
        fetch_start = time.perf_counter()
        url_host = urlparse(url).netloc

        while True:
            try:
                timeout = aiohttp.ClientTimeout(total=effective_timeout)
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
                        # Check if we should retry
                        if self._should_retry(response.status, attempt):
                            response_headers = dict(response.headers)
                            retry_after = self._parse_retry_after(response_headers)
                            backoff = self._calculate_backoff(attempt, retry_after)

                            if response.status == 429:
                                rate_limited = True
                                logger.warning(
                                    f"fetch.retry {url_host} HTTP 429 rate-limited "
                                    f"(attempt {attempt + 1}/{self.max_retries}, "
                                    f"backoff {backoff:.1f}s). "
                                    f"Remediation: reduce request rate or wait for retry window",
                                    event="fetch_retry",
                                    operation="fetch_url",
                                    stage="fetch",
                                    dependency="target_site",
                                    cause_type="HTTP429",
                                    impact="request_delayed_retrying",
                                    remediation="respect_retry_after_or_reduce_request_rate",
                                    url=url,
                                    attempt=attempt + 1,
                                    retry_after=retry_after,
                                    backoff=backoff,
                                )
                            else:
                                logger.warning(
                                    f"fetch.retry {url_host} HTTP {response.status} server error "
                                    f"(attempt {attempt + 1}/{self.max_retries}, "
                                    f"backoff {backoff:.1f}s). "
                                    f"Remediation: check target site health or try later",
                                    event="fetch_retry",
                                    operation="fetch_url",
                                    stage="fetch",
                                    dependency="target_site",
                                    cause_type="HTTPServerError",
                                    impact="request_delayed_retrying",
                                    remediation="retry_with_backoff_or_validate_target_availability",
                                    url=url,
                                    status=response.status,
                                    attempt=attempt + 1,
                                    backoff=backoff,
                                )

                            await asyncio.sleep(backoff)
                            attempt += 1
                            continue

                        # Detect encoding
                        encoding = response.charset or "utf-8"

                        # Read content
                        content = await response.text(encoding=encoding)

                        # Get content type
                        content_type = response.headers.get("Content-Type")

                        # Convert headers to dict
                        response_headers = dict(response.headers)

                        # Set error for HTTP error status codes
                        error_msg = None
                        if response.status >= 400:
                            reason = response.reason or "Unknown"
                            error_msg = f"HTTP {response.status} {reason}"

                        duration_ms = int((time.perf_counter() - fetch_start) * 1000)
                        logger.info(
                            f"fetch.done {url_host} HTTP {response.status} "
                            f"{len(content):,} bytes {duration_ms}ms"
                            + (f" (retries={attempt})" if attempt else ""),
                            url=url,
                            status=response.status,
                            content_length=len(content),
                            duration_ms=duration_ms,
                            retries=attempt,
                            backend="aiohttp",
                        )

                        return FetchResult(
                            url=str(response.url),  # Final URL after redirects
                            status_code=response.status,
                            content=content,
                            content_type=content_type,
                            headers=response_headers,
                            encoding=encoding,
                            error=error_msg,
                            retry_count=attempt,
                            rate_limited=rate_limited,
                        )

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(
                        f"fetch.error {url_host} {type(e).__name__}: {last_error[:120]} "
                        f"(attempt {attempt + 1}/{self.max_retries}, "
                        f"backoff {backoff:.1f}s). "
                        f"Remediation: check network connectivity or target availability",
                        event="fetch_retry",
                        operation="fetch_url",
                        stage="fetch",
                        dependency="target_site",
                        cause_type=type(e).__name__,
                        impact="request_delayed_retrying",
                        remediation="retry_with_backoff_or_check_network_connectivity",
                        url=url,
                        error=last_error,
                        attempt=attempt + 1,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    attempt += 1
                    continue
                else:
                    duration_ms = int((time.perf_counter() - fetch_start) * 1000)
                    logger.error(
                        f"fetch.failed {url_host} {type(e).__name__} after {attempt + 1} "
                        f"attempts ({duration_ms}ms total): {last_error[:200]}. "
                        f"Remediation: verify target is reachable from container, "
                        f"check DNS/firewall, or try again later",
                        event="fetch_failed",
                        operation="fetch_url",
                        stage="fetch",
                        dependency="target_site",
                        cause_type=type(e).__name__,
                        impact="request_failed",
                        remediation="check_target_or_network_health_then_retry",
                        url=url,
                        error=last_error,
                        duration_ms=duration_ms,
                        attempts=attempt + 1,
                    )
                    return FetchResult(
                        url=url,
                        status_code=0,
                        content="",
                        error=f"HTTP error after {attempt + 1} attempts: {last_error}",
                        retry_count=attempt,
                        rate_limited=rate_limited,
                    )

            except Exception as e:
                duration_ms = int((time.perf_counter() - fetch_start) * 1000)
                logger.error(
                    f"fetch.failed {url_host} unexpected {type(e).__name__}: "
                    f"{str(e)[:200]} ({duration_ms}ms). "
                    f"Remediation: inspect the full traceback, check if URL is valid, "
                    f"and report issue if persistent",
                    event="fetch_failed",
                    operation="fetch_url",
                    stage="fetch",
                    dependency="target_site",
                    cause_type=type(e).__name__,
                    impact="request_failed",
                    remediation="inspect_exception_and_retry_or_report_issue",
                    url=url,
                    error=str(e),
                    duration_ms=duration_ms,
                )
                return FetchResult(
                    url=url,
                    status_code=0,
                    content="",
                    error=f"Unexpected error: {str(e)}",
                    retry_count=attempt,
                    rate_limited=rate_limited,
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
    timeout_seconds: Optional[float] = None,
) -> FetchResult:
    """Convenience function to fetch a URL.

    Args:
        url: The URL to fetch
        rotate_user_agent: If True, rotate to a new User-Agent
        additional_headers: Extra headers to include
        timeout_seconds: Optional timeout override for this request

    Returns:
        FetchResult with the response data or error
    """
    fetcher = get_fetcher()
    return await fetcher.fetch(url, rotate_user_agent, additional_headers, timeout_seconds)
