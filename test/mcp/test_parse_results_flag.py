"""Tests for parse_results flag on the get_content MCP tool.

Validates that:
1. parse_results=true (default) runs the news parser and returns feed_meta + stories.
2. parse_results=false returns raw crawl output (pages, text, links, etc).
3. The parser runs for ALL depths (depth=1, 2, 3) — no special-casing.
4. Parser errors return PARSE_ERROR error code.
5. source_profile_name is passed through to the parser.
6. Parsed output is stored correctly when session=true.
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
        chunks.append(chunk)
    raw = "".join(chunks)
    return json.loads(raw)


class TestParseResultsDefault:
    """parse_results defaults to true — parser runs automatically."""

    def setup_method(self):
        reset_scraping_state()
        _reset_session_manager()

    def teardown_method(self):
        reset_scraping_state()
        _reset_session_manager()

    @pytest.mark.asyncio
    async def test_depth_1_parsed_has_feed_meta(self, html_fixture_server):
        """depth=1 with parse_results=true returns parser output with feed_meta."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {"url": url})
        data = get_mcp_result_data(result)

        assert "feed_meta" in data, "Parsed output must have feed_meta"
        assert "stories" in data, "Parsed output must have stories"
        assert isinstance(data["stories"], list)
        assert data["feed_meta"]["pages_crawled"] == 1
        assert data["crawl_depth"] == 1

    @pytest.mark.asyncio
    async def test_depth_2_parsed_has_feed_meta(self, html_fixture_server):
        """depth=2 with parse_results=true returns parser output with feed_meta."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 2,
        })
        data = get_mcp_result_data(result)

        assert "feed_meta" in data, "Parsed output must have feed_meta"
        assert "stories" in data, "Parsed output must have stories"
        assert data["feed_meta"]["pages_crawled"] >= 2
        assert data["crawl_depth"] == 2
        # Multi-page parsed output should retain raw_summary from crawl
        assert "raw_summary" in data
        assert data["raw_summary"]["total_pages"] >= 2

    @pytest.mark.asyncio
    async def test_depth_1_parsed_no_raw_pages(self, html_fixture_server):
        """Parsed output should not expose raw pages array."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {"url": url})
        data = get_mcp_result_data(result)

        # Parser output has feed_meta + stories, not raw page keys
        assert "feed_meta" in data
        assert "title" not in data, "Raw page keys should not appear in parsed output"


class TestParseResultsFalse:
    """parse_results=false returns raw crawl data unchanged."""

    def setup_method(self):
        reset_scraping_state()
        _reset_session_manager()

    def teardown_method(self):
        reset_scraping_state()
        _reset_session_manager()

    @pytest.mark.asyncio
    async def test_depth_1_raw_has_title_and_text(self, html_fixture_server):
        """depth=1, parse_results=false returns raw page dict."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "parse_results": False,
        })
        data = get_mcp_result_data(result)

        assert "title" in data
        assert "text" in data
        assert "feed_meta" not in data, "Raw output must not have feed_meta"

    @pytest.mark.asyncio
    async def test_depth_2_raw_has_pages(self, html_fixture_server):
        """depth=2, parse_results=false returns raw crawl with pages array."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "depth": 2,
            "max_pages_per_level": 2,
            "parse_results": False,
        })
        data = get_mcp_result_data(result)

        assert "pages" in data
        assert "summary" in data
        assert "feed_meta" not in data


class TestParseResultsWithSession:
    """Session stores whichever payload the caller receives (parsed or raw)."""

    def setup_method(self):
        reset_scraping_state()
        _reset_session_manager()

    def teardown_method(self):
        reset_scraping_state()
        _reset_session_manager()

    @pytest.mark.asyncio
    async def test_parsed_output_stored_in_session(self, html_fixture_server):
        """session=true + parse_results=true stores parsed feed in session."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "session": True,
        })
        data = get_mcp_result_data(result)

        assert data["success"] is True
        assert "session_id" in data

        # Retrieve stored content and verify it is the parsed feed
        content = get_session_content(data["session_id"])
        assert "feed_meta" in content, "Session should store parsed feed"
        assert "stories" in content

    @pytest.mark.asyncio
    async def test_raw_output_stored_in_session(self, html_fixture_server):
        """session=true + parse_results=false stores raw page data in session."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "session": True,
            "parse_results": False,
        })
        data = get_mcp_result_data(result)

        assert data["success"] is True
        assert "session_id" in data

        content = get_session_content(data["session_id"])
        assert "title" in content, "Session should store raw page data"
        assert "feed_meta" not in content


class TestSourceProfileName:
    """source_profile_name is passed through to the parser."""

    def setup_method(self):
        reset_scraping_state()
        _reset_session_manager()

    def teardown_method(self):
        reset_scraping_state()
        _reset_session_manager()

    @pytest.mark.asyncio
    async def test_source_profile_in_feed_meta(self, html_fixture_server):
        """source_profile_name appears in feed_meta when provided."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {
            "url": url,
            "source_profile_name": "scmp",
        })
        data = get_mcp_result_data(result)

        assert "feed_meta" in data
        assert data["feed_meta"]["source_profile"] == "scmp"

    @pytest.mark.asyncio
    async def test_generic_profile_without_source_profile_name(self, html_fixture_server):
        """Without source_profile_name, parser uses the generic fallback."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {"url": url})
        data = get_mcp_result_data(result)

        assert "feed_meta" in data
        assert data["feed_meta"]["source_profile"] == "generic"


class TestParseError:
    """Parser failures return PARSE_ERROR error code."""

    def setup_method(self):
        reset_scraping_state()
        _reset_session_manager()

    def teardown_method(self):
        reset_scraping_state()
        _reset_session_manager()

    @pytest.mark.asyncio
    async def test_parser_failure_returns_parse_error(self, html_fixture_server, monkeypatch):
        """If the parser throws, we get PARSE_ERROR."""
        from app.mcp_server.mcp_server import handle_call_tool

        # Patch NewsParser.parse to always raise
        def exploding_parse(self, crawl_result):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(
            "app.processing.news_parser.NewsParser.parse",
            exploding_parse,
        )

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {"url": url})
        data = get_mcp_result_data(result)

        assert data.get("success") is False
        assert data["error_code"] == "PARSE_ERROR"
        assert "kaboom" in data["error"]
