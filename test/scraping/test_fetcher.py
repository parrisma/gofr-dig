"""Tests for HTTP fetcher module.

Tests the async HTTP fetching with anti-detection support.
"""

import pytest

from app.scraping import (
    AntiDetectionProfile,
    FetchResult,
    HTTPFetcher,
    fetch_url,
    get_scraping_state,
    reset_scraping_state,
)


class TestFetchResult:
    """Tests for FetchResult dataclass."""

    def test_success_for_200(self):
        """Test that 200 status is success."""
        result = FetchResult(url="http://example.com", status_code=200, content="OK")
        assert result.success is True

    def test_success_for_301(self):
        """Test that 3xx status is success (redirect followed)."""
        result = FetchResult(url="http://example.com", status_code=301, content="")
        assert result.success is True

    def test_failure_for_404(self):
        """Test that 404 is not success."""
        result = FetchResult(url="http://example.com", status_code=404, content="")
        assert result.success is False

    def test_failure_for_error(self):
        """Test that error message means failure."""
        result = FetchResult(
            url="http://example.com",
            status_code=200,
            content="",
            error="Connection failed",
        )
        assert result.success is False

    def test_failure_for_zero_status(self):
        """Test that status 0 (no response) is failure."""
        result = FetchResult(url="http://example.com", status_code=0, content="")
        assert result.success is False


class TestHTTPFetcher:
    """Tests for HTTPFetcher class."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()

    def teardown_method(self):
        """Reset state after each test."""
        reset_scraping_state()

    @pytest.mark.asyncio
    async def test_fetch_from_fixture_server(self, html_fixture_server):
        """Test fetching from the HTML fixture server."""
        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("index.html")

        result = await fetcher.fetch(url)

        assert result.success
        assert result.status_code == 200
        assert "ACME Corporation" in result.content
        assert result.content_type is not None

    @pytest.mark.asyncio
    async def test_fetch_products_page(self, html_fixture_server):
        """Test fetching products page."""
        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("products.html")

        result = await fetcher.fetch(url)

        assert result.success
        assert "Widget Pro 3000" in result.content

    @pytest.mark.asyncio
    async def test_fetch_chinese_content(self, html_fixture_server):
        """Test fetching Chinese content with correct encoding."""
        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("chinese.html")

        result = await fetcher.fetch(url)

        assert result.success
        assert "欢迎访问" in result.content
        assert "ACME公司" in result.content

    @pytest.mark.asyncio
    async def test_fetch_japanese_content(self, html_fixture_server):
        """Test fetching Japanese content with correct encoding."""
        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("japanese.html")

        result = await fetcher.fetch(url)

        assert result.success
        assert "ようこそ" in result.content
        assert "製品" in result.content

    @pytest.mark.asyncio
    async def test_fetch_404_returns_failure(self, html_fixture_server):
        """Test that 404 returns a failure result."""
        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("nonexistent.html")

        result = await fetcher.fetch(url)

        assert not result.success
        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_fetch_invalid_url_scheme(self):
        """Test that invalid URL scheme returns error."""
        fetcher = HTTPFetcher()

        result = await fetcher.fetch("ftp://example.com/file.txt")

        assert not result.success
        assert result.error is not None and "Invalid URL scheme" in result.error

    @pytest.mark.asyncio
    async def test_fetch_uses_antidetection_headers(self, html_fixture_server):
        """Test that fetch uses headers from anti-detection state."""
        # Set stealth profile
        state = get_scraping_state()
        state.antidetection_profile = AntiDetectionProfile.STEALTH

        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("index.html")

        result = await fetcher.fetch(url)

        assert result.success
        # Can't directly verify headers sent, but verify fetch works
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_fetch_with_custom_headers(self, html_fixture_server):
        """Test that custom headers are added to request."""
        state = get_scraping_state()
        state.antidetection_profile = AntiDetectionProfile.CUSTOM
        state.custom_headers = {"X-Custom": "test-value"}
        state.custom_user_agent = "TestBot/1.0"

        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("index.html")

        result = await fetcher.fetch(url)

        assert result.success

    @pytest.mark.asyncio
    async def test_fetch_with_additional_headers(self, html_fixture_server):
        """Test passing additional headers to fetch."""
        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("index.html")

        result = await fetcher.fetch(
            url,
            additional_headers={"X-Request-ID": "test-123"},
        )

        assert result.success

    @pytest.mark.asyncio
    async def test_fetch_returns_response_headers(self, html_fixture_server):
        """Test that response headers are returned."""
        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("index.html")

        result = await fetcher.fetch(url)

        assert result.success
        assert result.headers is not None
        assert "Content-Type" in result.headers

    @pytest.mark.asyncio
    async def test_fetch_connection_refused(self):
        """Test that connection refused is handled gracefully."""
        fetcher = HTTPFetcher(timeout=2.0)

        # Try to connect to a port that's not listening
        result = await fetcher.fetch("http://127.0.0.1:59999/test")

        assert not result.success
        assert result.error is not None
        assert "error" in result.error.lower() or "refused" in result.error.lower()


class TestFetchUrlFunction:
    """Tests for the fetch_url convenience function."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()

    def teardown_method(self):
        """Reset state after each test."""
        reset_scraping_state()

    @pytest.mark.asyncio
    async def test_fetch_url_works(self, html_fixture_server):
        """Test the convenience function."""
        url = html_fixture_server.get_url("index.html")

        result = await fetch_url(url)

        assert result.success
        assert "ACME" in result.content

    @pytest.mark.asyncio
    async def test_fetch_url_with_rotation(self, html_fixture_server):
        """Test fetch_url with User-Agent rotation."""
        url = html_fixture_server.get_url("products.html")

        result = await fetch_url(url, rotate_user_agent=True)

        assert result.success


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()

    def teardown_method(self):
        """Reset state after each test."""
        reset_scraping_state()

    @pytest.mark.asyncio
    async def test_rate_limiting_applies_delay(self, html_fixture_server):
        """Test that rate limiting delays subsequent requests."""
        import time

        # Set a measurable delay
        state = get_scraping_state()
        state.rate_limit_delay = 0.2  # 200ms

        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("index.html")

        # First request
        start = time.time()
        await fetcher.fetch(url)
        _ = time.time() - start  # noqa: F841 - baseline timing not needed for assertion

        # Second request should be delayed
        start = time.time()
        await fetcher.fetch(url)
        second_elapsed = time.time() - start

        # Second request should take at least the rate limit delay
        # (minus a small tolerance for timing variations)
        assert second_elapsed >= 0.15  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_no_rate_limit_when_zero(self, html_fixture_server):
        """Test that rate limiting is disabled when delay is 0."""
        import time

        state = get_scraping_state()
        state.rate_limit_delay = 0

        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("index.html")

        # Both requests should complete quickly
        start = time.time()
        await fetcher.fetch(url)
        await fetcher.fetch(url)
        elapsed = time.time() - start

        # Both should complete much faster than if rate limited
        assert elapsed < 0.5  # Should be nearly instant


class TestContentTypes:
    """Tests for different content types."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()

    def teardown_method(self):
        """Reset state after each test."""
        reset_scraping_state()

    @pytest.mark.asyncio
    async def test_fetch_robots_txt(self, html_fixture_server):
        """Test fetching plain text (robots.txt)."""
        fetcher = HTTPFetcher()
        url = html_fixture_server.get_url("robots.txt")

        result = await fetcher.fetch(url)

        assert result.success
        assert "User-agent:" in result.content
        assert "Disallow:" in result.content
