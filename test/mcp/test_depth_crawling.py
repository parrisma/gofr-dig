"""Tests for depth crawling functionality in get_content MCP tool.

Phase 8: Tests for multi-level crawling with depth parameter.

These tests verify:
1. Depth 2 and 3 crawling returns pages array
2. Top-level content fields populated from root page (REGRESSION TEST)
3. max_pages_per_level is respected
4. Duplicate URLs are not visited twice
5. Dead links don't break the crawl
6. Summary statistics are accurate
"""

import json
from typing import Any, List

import pytest

from app.scraping.state import reset_scraping_state


def get_mcp_result_data(result: Any) -> dict:
    """Extract JSON data from MCP tool result."""
    result_list: List[Any] = result
    return json.loads(result_list[0].text)


class TestDepthCrawling:
    """Tests for depth crawling functionality."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()

    def teardown_method(self):
        """Reset state after each test."""
        reset_scraping_state()

    @pytest.mark.asyncio
    async def test_depth_1_same_as_default(self, html_fixture_server):
        """Test depth=1 returns same structure as default (no pages array)."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        
        # Default call (no depth parameter)
        result_default = await handle_call_tool("get_content", {"url": url})
        data_default = get_mcp_result_data(result_default)
        
        # Reset state for second call
        reset_scraping_state()
        
        # Explicit depth=1
        result_depth1 = await handle_call_tool("get_content", {"url": url, "depth": 1})
        data_depth1 = get_mcp_result_data(result_depth1)
        
        # Both should have same structure (no pages array)
        assert "pages" not in data_default
        assert "pages" not in data_depth1
        assert data_default["title"] == data_depth1["title"]
        assert data_default["url"] == data_depth1["url"]

    @pytest.mark.asyncio
    async def test_depth_2_returns_pages_array(self, html_fixture_server):
        """Test depth=2 returns pages array with root and linked pages."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 3,
        })
        data = get_mcp_result_data(result)
        
        assert data["success"] is True
        assert "pages" in data
        assert len(data["pages"]) > 1, "Expected multiple pages at depth 2"
        
        # Verify depth metadata
        assert data["crawl_depth"] == 2
        assert data["max_pages_per_level"] == 3
        
        # Root page should be depth 1
        assert data["pages"][0]["depth"] == 1
        
        # At least one page should be depth 2
        depth_2_pages = [p for p in data["pages"] if p.get("depth") == 2]
        assert len(depth_2_pages) > 0, "Expected at least one depth 2 page"

    @pytest.mark.asyncio
    async def test_depth_3_returns_nested_links(self, html_fixture_server):
        """Test depth=3 follows links to third level."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 3,
            "max_pages_per_level": 3,
        })
        data = get_mcp_result_data(result)
        
        assert data["success"] is True
        assert data["crawl_depth"] == 3
        
        # Check pages_by_depth summary
        pages_by_depth = data["summary"]["pages_by_depth"]
        assert "1" in pages_by_depth
        assert pages_by_depth["1"] == 1  # Only root at depth 1

    @pytest.mark.asyncio
    async def test_depth_crawl_has_top_level_content(self, html_fixture_server):
        """
        REGRESSION TEST: Ensure depth>1 response includes top-level content fields.
        
        Bug: Multi-page responses may have pages[] but empty top-level
        url/title/text fields, breaking LLM agents expecting consistent structure.
        """
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 3,
        })
        data = get_mcp_result_data(result)
        
        # These fields MUST be present at top level, not just in pages[0]
        assert data["success"] is True
        assert data["url"] is not None, "Top-level 'url' field missing"
        assert data["url"] == url, "Top-level URL doesn't match request URL"
        assert data["title"] is not None, "Top-level 'title' field missing"
        assert len(data.get("text", "")) > 0, "Top-level 'text' field empty"
        
        # Pages array should also exist
        assert "pages" in data
        assert len(data["pages"]) >= 1
        
        # Top-level should match root page (pages[0])
        root_page = data["pages"][0]
        assert data["url"] == root_page["url"], "Top-level URL doesn't match root page"
        assert data["title"] == root_page["title"], "Top-level title doesn't match root page"

    @pytest.mark.asyncio
    async def test_depth_crawl_has_top_level_headings_links_meta(self, html_fixture_server):
        """Test that top-level also includes headings, links, and meta from root page."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 2,
        })
        data = get_mcp_result_data(result)
        
        # Check optional fields are copied from root
        root_page = data["pages"][0]
        
        if root_page.get("headings"):
            assert "headings" in data, "Top-level 'headings' missing but root has them"
        if root_page.get("links"):
            assert "links" in data, "Top-level 'links' missing but root has them"
        if root_page.get("meta"):
            assert "meta" in data, "Top-level 'meta' missing but root has them"

    @pytest.mark.asyncio
    async def test_max_pages_per_level_respected(self, html_fixture_server):
        """Test that max_pages_per_level limits pages fetched at each depth."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 2,
        })
        data = get_mcp_result_data(result)
        
        # Count pages at depth 2
        depth_2_pages = [p for p in data["pages"] if p.get("depth") == 2]
        assert len(depth_2_pages) <= 2, f"Expected max 2 pages at depth 2, got {len(depth_2_pages)}"
        
        # Summary should match
        assert data["summary"]["pages_by_depth"].get("2", 0) <= 2

    @pytest.mark.asyncio
    async def test_depth_crawl_avoids_duplicate_urls(self, html_fixture_server):
        """Test that same URL is not fetched twice during crawl."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 3,
            "max_pages_per_level": 5,
        })
        data = get_mcp_result_data(result)
        
        # Extract all URLs from pages
        page_urls = [p["url"] for p in data["pages"]]
        
        # Check for duplicates (normalized)
        normalized_urls = [u.rstrip("/") for u in page_urls]
        assert len(normalized_urls) == len(set(normalized_urls)), \
            f"Found duplicate URLs in crawl: {normalized_urls}"

    @pytest.mark.asyncio
    async def test_depth_crawl_handles_dead_links(self, html_fixture_server):
        """Test that 404 links don't break the crawl."""
        from app.mcp_server.mcp_server import handle_call_tool

        # external-links.html may contain links to non-existent pages
        url = html_fixture_server.get_url("external-links.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 5,
        })
        data = get_mcp_result_data(result)
        
        # Crawl should succeed even if some links fail
        assert data["success"] is True
        assert len(data["pages"]) >= 1, "Should have at least root page"

    @pytest.mark.asyncio
    async def test_depth_summary_accurate(self, html_fixture_server):
        """Test that summary statistics are accurate."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 3,
        })
        data = get_mcp_result_data(result)
        
        # Verify summary matches actual data
        assert data["summary"]["total_pages"] == len(data["pages"])
        
        # Verify pages_by_depth sums to total
        depth_sum = sum(int(v) for v in data["summary"]["pages_by_depth"].values())
        assert depth_sum == data["summary"]["total_pages"]
        
        # Verify total_text_length is reasonable
        actual_text_length = sum(len(p.get("text", "")) for p in data["pages"])
        assert data["summary"]["total_text_length"] == actual_text_length

    @pytest.mark.asyncio
    async def test_depth_parameter_validation_min(self, html_fixture_server):
        """Test that depth < 1 is rejected or normalized."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 0,
        })
        data = get_mcp_result_data(result)
        
        # Should either error or treat as depth=1 (no pages array)
        # Current implementation clamps to 1
        assert "error" not in data or "pages" not in data

    @pytest.mark.asyncio
    async def test_depth_parameter_validation_max(self, html_fixture_server):
        """Test that depth > 3 is clamped to 3."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 10,  # Beyond maximum
            "max_pages_per_level": 2,
        })
        data = get_mcp_result_data(result)
        
        # Should be clamped to 3
        assert data["success"] is True
        assert data["crawl_depth"] == 3

    @pytest.mark.asyncio
    async def test_max_pages_per_level_validation(self, html_fixture_server):
        """Test that max_pages_per_level is validated within bounds."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        
        # Test with 0 (should be clamped to 1)
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 0,
        })
        data = get_mcp_result_data(result)
        assert data["success"] is True
        # Should have clamped to minimum (1)
        assert data["max_pages_per_level"] >= 1

    @pytest.mark.asyncio
    async def test_depth_crawl_with_selector(self, html_fixture_server):
        """Test that selector works with depth crawling."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 2,
            "selector": "#content",
        })
        data = get_mcp_result_data(result)
        
        assert data["success"] is True
        # Selector should apply to all pages
        for page in data["pages"]:
            if page.get("success"):
                # Content should be from #content section
                assert page.get("text") is not None


class TestDepthCrawlingEdgeCases:
    """Edge case tests for depth crawling."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()

    def teardown_method(self):
        """Reset state after each test."""
        reset_scraping_state()

    @pytest.mark.asyncio
    async def test_depth_crawl_on_page_with_no_internal_links(self, html_fixture_server):
        """Test depth crawl on a page with no internal links."""
        from app.mcp_server.mcp_server import handle_call_tool

        # external-links.html only has external links
        url = html_fixture_server.get_url("external-links.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 5,
        })
        data = get_mcp_result_data(result)
        
        assert data["success"] is True
        # Should have only root page since no internal links
        # (may have some depending on fixture content)
        assert len(data["pages"]) >= 1
        assert data["summary"]["total_pages"] >= 1

    @pytest.mark.asyncio
    async def test_depth_crawl_root_page_failure(self):
        """Test that failure to fetch root page returns error."""
        from app.mcp_server.mcp_server import handle_call_tool

        # Invalid URL that will fail
        result = await handle_call_tool("get_content", {
            "url": "http://127.0.0.1:9999/nonexistent.html",
            "depth": 2,
        })
        data = get_mcp_result_data(result)
        
        # Should fail gracefully, not crash
        assert data.get("success") is False or "error" in data
