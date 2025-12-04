"""Tests for robots.txt compliance.

Tests the robots.txt parsing and URL checking functionality.
"""

import json
from typing import Any, List

import pytest

from app.scraping.robots import (
    RobotRule,
    RobotRules,
    RobotsChecker,
    RobotsFile,
    RobotsParser,
    get_robots_checker,
    reset_robots_checker,
)
from app.scraping.state import get_scraping_state, reset_scraping_state


def get_mcp_result_data(result: Any) -> dict:
    """Extract JSON data from MCP tool result."""
    result_list: List[Any] = result  # type: ignore[assignment]
    return json.loads(result_list[0].text)  # type: ignore[union-attr]


class TestRobotRule:
    """Tests for RobotRule matching."""

    def test_exact_match(self):
        """Test exact path matching."""
        rule = RobotRule(path="/admin/", allow=False)
        assert rule.matches("/admin/")
        assert rule.matches("/admin/page")
        assert not rule.matches("/admin")  # No trailing slash
        assert not rule.matches("/administrator/")

    def test_prefix_match(self):
        """Test prefix path matching."""
        rule = RobotRule(path="/private", allow=False)
        assert rule.matches("/private")
        assert rule.matches("/private/")
        assert rule.matches("/private/data")
        assert not rule.matches("/pub")

    def test_wildcard_match(self):
        """Test wildcard pattern matching."""
        rule = RobotRule(path="/api/*/data", allow=False)
        assert rule.matches("/api/v1/data")
        assert rule.matches("/api/v2/data")
        assert rule.matches("/api/test/data")

    def test_end_anchor(self):
        """Test end anchor ($) matching."""
        rule = RobotRule(path="/*.pdf$", allow=False)
        assert rule.matches("/document.pdf")
        assert rule.matches("/path/to/file.pdf")
        assert not rule.matches("/document.pdf.bak")

    def test_empty_disallow_matches_nothing(self):
        """Test that empty disallow matches nothing (allows all)."""
        # Empty path Disallow matches nothing (allows all paths)
        # Empty path Allow matches all paths
        rule_allow = RobotRule(path="", allow=True)
        assert rule_allow.matches("/anything")


class TestRobotRules:
    """Tests for RobotRules (user-agent specific rules)."""

    def test_first_matching_rule_wins(self):
        """Test that first matching rule determines access."""
        rules = RobotRules(
            user_agent="*",
            rules=[
                RobotRule(path="/admin/public/", allow=True),
                RobotRule(path="/admin/", allow=False),
            ],
        )

        assert rules.is_allowed("/admin/public/page")  # Allow wins
        assert not rules.is_allowed("/admin/private")  # Disallow wins
        assert rules.is_allowed("/other")  # No match = allow

    def test_default_allow_when_no_match(self):
        """Test that access is allowed when no rules match."""
        rules = RobotRules(
            user_agent="*",
            rules=[RobotRule(path="/private/", allow=False)],
        )

        assert rules.is_allowed("/public/page")

    def test_crawl_delay(self):
        """Test crawl delay retrieval."""
        rules = RobotRules(user_agent="*", crawl_delay=2.5)
        assert rules.crawl_delay == 2.5


class TestRobotsParser:
    """Tests for RobotsParser."""

    def test_parse_basic_robots(self):
        """Test parsing basic robots.txt."""
        content = """
User-agent: *
Disallow: /admin/
Disallow: /private/
Allow: /admin/public/
"""
        parser = RobotsParser()
        robots = parser.parse(content)

        assert "*" in robots.rules_by_agent
        rules = robots.rules_by_agent["*"]
        assert len(rules.rules) == 3

    def test_parse_multiple_user_agents(self):
        """Test parsing multiple user-agent blocks."""
        content = """
User-agent: Googlebot
Disallow: /no-google/

User-agent: Bingbot
Disallow: /no-bing/

User-agent: *
Disallow: /private/
"""
        parser = RobotsParser()
        robots = parser.parse(content)

        assert "Googlebot" in robots.rules_by_agent
        assert "Bingbot" in robots.rules_by_agent
        assert "*" in robots.rules_by_agent

    def test_parse_crawl_delay(self):
        """Test parsing crawl-delay directive."""
        content = """
User-agent: *
Disallow: /admin/
Crawl-delay: 2
"""
        parser = RobotsParser()
        robots = parser.parse(content)

        rules = robots.rules_by_agent["*"]
        assert rules.crawl_delay == 2.0

    def test_parse_sitemap(self):
        """Test parsing sitemap directive."""
        content = """
User-agent: *
Disallow: /private/

Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap2.xml
"""
        parser = RobotsParser()
        robots = parser.parse(content)

        assert len(robots.sitemaps) == 2
        assert "https://example.com/sitemap.xml" in robots.sitemaps

    def test_parse_with_comments(self):
        """Test that comments are ignored."""
        content = """
# This is a comment
User-agent: *  # Another comment
Disallow: /admin/  # Disallow admin
"""
        parser = RobotsParser()
        robots = parser.parse(content)

        assert "*" in robots.rules_by_agent

    def test_parse_fixture_robots(self):
        """Test parsing the test fixture robots.txt."""
        content = """
# robots.txt for ACME Corp Test Fixture
User-agent: *
Allow: /
Allow: /products.html
Disallow: /admin/
Disallow: /api/
Disallow: /private/

Crawl-delay: 1

User-agent: BadBot
Disallow: /

Sitemap: https://www.acme-corp.example.com/sitemap.xml
"""
        parser = RobotsParser()
        robots = parser.parse(content)

        # Check wildcard rules
        assert robots.is_allowed("/products.html", "*")
        assert not robots.is_allowed("/admin/page", "*")
        assert not robots.is_allowed("/api/v1/data", "*")

        # Check BadBot rules
        assert not robots.is_allowed("/", "BadBot")
        assert not robots.is_allowed("/products.html", "BadBot")

        # Check crawl delay
        assert robots.get_crawl_delay("*") == 1.0

        # Check sitemap
        assert len(robots.sitemaps) == 1


class TestRobotsFile:
    """Tests for RobotsFile."""

    def test_get_rules_for_exact_agent(self):
        """Test getting rules for exact user-agent match."""
        robots = RobotsFile(url="")
        robots.rules_by_agent["Googlebot"] = RobotRules(
            user_agent="Googlebot",
            rules=[RobotRule(path="/", allow=False)],
        )
        robots.rules_by_agent["*"] = RobotRules(
            user_agent="*",
            rules=[RobotRule(path="/private/", allow=False)],
        )

        # Exact match
        rules = robots.get_rules_for_agent("Googlebot")
        assert rules.user_agent == "Googlebot"

    def test_get_rules_for_prefix_agent(self):
        """Test getting rules for user-agent prefix match."""
        robots = RobotsFile(url="")
        robots.rules_by_agent["Googlebot"] = RobotRules(
            user_agent="Googlebot",
            rules=[RobotRule(path="/", allow=False)],
        )

        # Prefix match
        rules = robots.get_rules_for_agent("Googlebot/2.1")
        assert rules.user_agent == "Googlebot"

    def test_fallback_to_wildcard(self):
        """Test fallback to * rules when no match."""
        robots = RobotsFile(url="")
        robots.rules_by_agent["*"] = RobotRules(
            user_agent="*",
            rules=[RobotRule(path="/private/", allow=False)],
        )

        rules = robots.get_rules_for_agent("UnknownBot")
        assert rules.user_agent == "*"

    def test_is_allowed(self):
        """Test is_allowed method."""
        parser = RobotsParser()
        robots = parser.parse("""
User-agent: *
Disallow: /admin/
Allow: /admin/public/
""")

        assert robots.is_allowed("https://example.com/page")
        assert robots.is_allowed("https://example.com/admin/public/doc")
        assert not robots.is_allowed("https://example.com/admin/private")


class TestRobotsChecker:
    """Tests for RobotsChecker with HTTP fetching."""

    def setup_method(self):
        """Reset checker before each test."""
        reset_robots_checker()
        reset_scraping_state()

    def teardown_method(self):
        """Reset after tests."""
        reset_robots_checker()
        reset_scraping_state()

    @pytest.mark.asyncio
    async def test_fetch_and_check_robots(self, html_fixture_server):
        """Test fetching and checking against robots.txt."""
        checker = get_robots_checker()

        # Check allowed URL
        url = html_fixture_server.get_url("products.html")
        allowed, reason = await checker.is_allowed(url)
        assert allowed

        # Check disallowed URL
        url_admin = html_fixture_server.get_url("admin/page")
        allowed, reason = await checker.is_allowed(url_admin)
        assert not allowed
        assert reason is not None and "Disallowed" in reason

    @pytest.mark.asyncio
    async def test_get_crawl_delay(self, html_fixture_server):
        """Test getting crawl delay from robots.txt."""
        checker = get_robots_checker()

        url = html_fixture_server.get_url("index.html")
        delay = await checker.get_crawl_delay(url)

        # Our fixture has Crawl-delay: 1
        assert delay == 1.0

    @pytest.mark.asyncio
    async def test_cache_robots(self, html_fixture_server):
        """Test that robots.txt is cached."""
        checker = get_robots_checker()

        url1 = html_fixture_server.get_url("page1.html")
        url2 = html_fixture_server.get_url("page2.html")

        # First fetch
        await checker.is_allowed(url1)

        # Second fetch should use cache (same domain)
        robots_url = checker.get_robots_url(url2)
        assert robots_url in checker._cache

    @pytest.mark.asyncio
    async def test_missing_robots_allows_all(self):
        """Test that missing robots.txt allows all URLs."""
        checker = RobotsChecker()

        # Use a URL that won't have robots.txt
        # This will fail to fetch, so it should allow all
        allowed, _ = await checker.is_allowed("http://127.0.0.1:59999/page")
        assert allowed  # Allow when robots.txt can't be fetched


class TestRobotsComplianceInTools:
    """Integration tests for robots.txt compliance in MCP tools."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()
        reset_robots_checker()

    def teardown_method(self):
        """Reset state after tests."""
        reset_scraping_state()
        reset_robots_checker()

    @pytest.mark.asyncio
    async def test_get_content_respects_robots(self, html_fixture_server):
        """Test that get_content respects robots.txt."""
        from app.mcp_server.mcp_server import handle_call_tool

        # Enable robots.txt checking (default)
        state = get_scraping_state()
        state.respect_robots_txt = True

        # Try to access disallowed path
        url = html_fixture_server.get_url("admin/secret.html")
        result = await handle_call_tool("get_content", {"url": url})

        data = get_mcp_result_data(result)
        assert "error" in data
        assert data.get("robots_blocked") is True

    @pytest.mark.asyncio
    async def test_get_content_allowed_when_robots_disabled(self, html_fixture_server):
        """Test that get_content ignores robots.txt when disabled."""
        from app.mcp_server.mcp_server import handle_call_tool

        # Disable robots.txt checking
        state = get_scraping_state()
        state.respect_robots_txt = False

        # Access would-be disallowed path (will 404, but not blocked by robots)
        url = html_fixture_server.get_url("admin/secret.html")
        result = await handle_call_tool("get_content", {"url": url})

        data = get_mcp_result_data(result)
        # Should get 404 error, not robots blocked
        assert data.get("robots_blocked") is not True

    @pytest.mark.asyncio
    async def test_get_structure_respects_robots(self, html_fixture_server):
        """Test that get_structure respects robots.txt."""
        from app.mcp_server.mcp_server import handle_call_tool

        # Enable robots.txt checking
        state = get_scraping_state()
        state.respect_robots_txt = True

        # Try to access disallowed path
        url = html_fixture_server.get_url("api/v1/data")
        result = await handle_call_tool("get_structure", {"url": url})

        data = get_mcp_result_data(result)
        assert "error" in data
        assert data.get("robots_blocked") is True

    @pytest.mark.asyncio
    async def test_set_antidetection_controls_robots(self, html_fixture_server):
        """Test that set_antidetection can enable/disable robots checking."""
        from app.mcp_server.mcp_server import handle_call_tool

        # Disable via set_antidetection
        await handle_call_tool(
            "set_antidetection",
            {"profile": "balanced", "respect_robots_txt": False},
        )

        state = get_scraping_state()
        assert state.respect_robots_txt is False

        # Re-enable
        await handle_call_tool(
            "set_antidetection",
            {"profile": "balanced", "respect_robots_txt": True},
        )

        state = get_scraping_state()
        assert state.respect_robots_txt is True

    @pytest.mark.asyncio
    async def test_allowed_paths_work(self, html_fixture_server):
        """Test that allowed paths are accessible."""
        from app.mcp_server.mcp_server import handle_call_tool

        # Enable robots.txt checking
        state = get_scraping_state()
        state.respect_robots_txt = True

        # Access allowed path
        url = html_fixture_server.get_url("products.html")
        result = await handle_call_tool("get_content", {"url": url})

        data = get_mcp_result_data(result)
        assert "error" not in data
        assert "Widget Pro" in data.get("text", "")
