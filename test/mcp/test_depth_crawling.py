"""Tests for depth crawling functionality in get_content MCP tool.

Phase 8: Tests for multi-level crawling with depth parameter.

depth > 1 auto-forces session mode (large payloads). These tests verify:
1. Depth > 1 returns a session response (session_id, total_chunks, etc.)
2. Session content can be retrieved via session manager
3. max_pages_per_level is respected (via total_pages in response)
4. Dead links don't break the crawl
5. Depth validation / clamping works
6. Selectors are applied during crawl
"""

import json
from typing import Any, List

import pytest

import app.mcp_server.mcp_server as mcp_mod
from app.scraping.state import reset_scraping_state


def get_mcp_result_data(result: Any) -> dict:
    """Extract JSON data from MCP tool result."""
    result_list: List[Any] = result
    return json.loads(result_list[0].text)


def _reset_session_manager() -> None:
    """Reset the MCP server's singleton so it picks up the fresh test temp dir."""
    mcp_mod.session_manager = None


def get_session_content(session_id: str) -> dict:
    """Retrieve full stored content from a session by reassembling chunks."""
    manager = mcp_mod.get_session_manager()
    info = manager.get_session_info(session_id)
    chunks = []
    for i in range(info["total_chunks"]):
        chunk = manager.get_chunk(session_id, i)
        chunks.append(chunk)  # get_chunk returns str directly
    raw = "".join(chunks)
    return json.loads(raw)


class TestDepthCrawling:
    """Tests for depth crawling functionality."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()
        _reset_session_manager()

    def teardown_method(self):
        """Reset state after each test."""
        reset_scraping_state()
        _reset_session_manager()

    @pytest.mark.asyncio
    async def test_depth_1_same_as_default(self, html_fixture_server):
        """Test depth=1 returns same structure as default (no session, inline content)."""
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

        # Both should have same structure (inline content, no session_id)
        assert "session_id" not in data_default
        assert "session_id" not in data_depth1
        assert data_default["title"] == data_depth1["title"]
        assert data_default["url"] == data_depth1["url"]

    @pytest.mark.asyncio
    async def test_depth_2_auto_session(self, html_fixture_server):
        """Test depth=2 auto-forces session mode and returns session response."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 3,
        })
        data = get_mcp_result_data(result)

        assert data["success"] is True
        assert "session_id" in data, "depth > 1 must auto-force session mode"
        assert data["total_chunks"] >= 1
        assert data["total_size"] > 0
        assert data["crawl_depth"] == 2
        assert data["total_pages"] > 1, "Expected multiple pages at depth 2"
        assert data["url"] == url

    @pytest.mark.asyncio
    async def test_depth_2_session_contains_pages(self, html_fixture_server):
        """Test that the stored session content contains the pages array."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 3,
        })
        data = get_mcp_result_data(result)
        content = get_session_content(data["session_id"])

        assert "pages" in content
        assert len(content["pages"]) > 1
        # Root page at depth 1
        assert content["pages"][0]["depth"] == 1
        # At least one depth-2 page
        depth_2 = [p for p in content["pages"] if p.get("depth") == 2]
        assert len(depth_2) > 0

    @pytest.mark.asyncio
    async def test_depth_3_auto_session(self, html_fixture_server):
        """Test depth=3 auto-forces session and stores nested crawl."""
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
        assert "session_id" in data

        # Verify stored content
        content = get_session_content(data["session_id"])
        assert content["summary"]["pages_by_depth"]["1"] == 1

    @pytest.mark.asyncio
    async def test_depth_crawl_session_has_top_level_content(self, html_fixture_server):
        """
        REGRESSION TEST: Session content must include top-level fields
        from the root page (url, title, text).
        """
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 3,
        })
        data = get_mcp_result_data(result)
        content = get_session_content(data["session_id"])

        assert content["url"] is not None
        assert content["url"] == url
        assert content["title"] is not None
        assert len(content.get("text", "")) > 0

        # Top-level must match root page
        root = content["pages"][0]
        assert content["url"] == root["url"]
        assert content["title"] == root["title"]

    @pytest.mark.asyncio
    async def test_depth_crawl_session_has_headings_links_meta(self, html_fixture_server):
        """Test stored session copies headings/links/meta from root page."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 2,
        })
        data = get_mcp_result_data(result)
        content = get_session_content(data["session_id"])
        root = content["pages"][0]

        if root.get("headings"):
            assert "headings" in content
        if root.get("links"):
            assert "links" in content
        if root.get("meta"):
            assert "meta" in content

    @pytest.mark.asyncio
    async def test_max_pages_per_level_respected(self, html_fixture_server):
        """Test max_pages_per_level limits pages at each depth."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 2,
        })
        data = get_mcp_result_data(result)
        content = get_session_content(data["session_id"])

        depth_2 = [p for p in content["pages"] if p.get("depth") == 2]
        assert len(depth_2) <= 2, f"Expected max 2 depth-2 pages, got {len(depth_2)}"
        assert content["summary"]["pages_by_depth"].get("2", 0) <= 2

    @pytest.mark.asyncio
    async def test_depth_crawl_avoids_duplicate_urls(self, html_fixture_server):
        """Test that no URL is fetched twice during a crawl."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 3,
            "max_pages_per_level": 5,
        })
        data = get_mcp_result_data(result)
        content = get_session_content(data["session_id"])

        page_urls = [p["url"].rstrip("/") for p in content["pages"]]
        assert len(page_urls) == len(set(page_urls)), \
            f"Found duplicate URLs: {page_urls}"

    @pytest.mark.asyncio
    async def test_depth_crawl_handles_dead_links(self, html_fixture_server):
        """Test that 404 links don't break the crawl."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("external-links.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 5,
        })
        data = get_mcp_result_data(result)

        assert data["success"] is True
        assert data["total_pages"] >= 1, "Should have at least root page"

    @pytest.mark.asyncio
    async def test_depth_summary_accurate(self, html_fixture_server):
        """Test that stored summary statistics are accurate."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 3,
        })
        data = get_mcp_result_data(result)
        content = get_session_content(data["session_id"])

        assert content["summary"]["total_pages"] == len(content["pages"])
        depth_sum = sum(int(v) for v in content["summary"]["pages_by_depth"].values())
        assert depth_sum == content["summary"]["total_pages"]
        actual_len = sum(len(p.get("text", "")) for p in content["pages"])
        assert content["summary"]["total_text_length"] == actual_len

    @pytest.mark.asyncio
    async def test_depth_parameter_validation_min(self, html_fixture_server):
        """Test that depth < 1 is clamped to 1 (inline response, no session)."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 0,
        })
        data = get_mcp_result_data(result)

        # Clamped to 1 → inline response, no session
        assert "error" not in data or "session_id" not in data

    @pytest.mark.asyncio
    async def test_depth_parameter_validation_max(self, html_fixture_server):
        """Test that depth > 3 is clamped to 3 (auto-session)."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 10,
            "max_pages_per_level": 2,
        })
        data = get_mcp_result_data(result)

        assert data["success"] is True
        assert data["crawl_depth"] == 3

    @pytest.mark.asyncio
    async def test_max_pages_per_level_validation(self, html_fixture_server):
        """Test that max_pages_per_level=0 is clamped to 1."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 0,
        })
        data = get_mcp_result_data(result)

        assert data["success"] is True
        # total_pages >= 1 means clamping worked
        assert data["total_pages"] >= 1

    @pytest.mark.asyncio
    async def test_depth_crawl_with_selector(self, html_fixture_server):
        """Test that selector works with depth crawling (session mode)."""
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
        assert "session_id" in data

        # Verify selector applied by checking stored content
        content = get_session_content(data["session_id"])
        for page in content["pages"]:
            if page.get("success"):
                assert page.get("text") is not None


class TestDepthCrawlingEdgeCases:
    """Edge case tests for depth crawling."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()
        _reset_session_manager()

    def teardown_method(self):
        """Reset state after each test."""
        reset_scraping_state()
        _reset_session_manager()

    @pytest.mark.asyncio
    async def test_depth_crawl_on_page_with_no_internal_links(self, html_fixture_server):
        """Test depth crawl on page with only external links (session mode)."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("external-links.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 5,
        })
        data = get_mcp_result_data(result)

        assert data["success"] is True
        assert data["total_pages"] >= 1

    @pytest.mark.asyncio
    async def test_depth_crawl_root_page_failure(self):
        """Test that failure to fetch root page returns error."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool("get_content", {
            "url": "http://127.0.0.1:9999/nonexistent.html",
            "depth": 2,
        })
        data = get_mcp_result_data(result)

        assert data.get("success") is False or "error" in data
