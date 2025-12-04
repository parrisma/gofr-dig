"""Tests for get_structure MCP tool.

Tests the structure analysis tool for web scraping.
"""

import json
from typing import Any, List

import pytest

from app.scraping.state import reset_scraping_state
from app.scraping.structure import StructureAnalyzer


def get_mcp_result_data(result: Any) -> dict:
    """Extract JSON data from MCP tool result."""
    result_list: List[Any] = result  # type: ignore[assignment]
    return json.loads(result_list[0].text)  # type: ignore[union-attr]


class TestStructureAnalyzer:
    """Tests for StructureAnalyzer class."""

    def test_analyze_title(self):
        """Test extracting page title."""
        html = """
        <html>
        <head><title>Test Page</title></head>
        <body><h1>Heading</h1></body>
        </html>
        """
        analyzer = StructureAnalyzer()
        structure = analyzer.analyze(html)

        assert structure.success
        assert structure.title == "Test Page"

    def test_analyze_language(self):
        """Test extracting language."""
        html = """
        <html lang="en-US">
        <body><p>English content</p></body>
        </html>
        """
        analyzer = StructureAnalyzer()
        structure = analyzer.analyze(html)

        assert structure.language == "en-US"

    def test_find_semantic_sections(self):
        """Test finding semantic sections."""
        html = """
        <html>
        <body>
            <header id="site-header">Header content</header>
            <nav id="main-nav">Navigation</nav>
            <main id="content">
                <article>Article content</article>
            </main>
            <aside>Sidebar</aside>
            <footer>Footer</footer>
        </body>
        </html>
        """
        analyzer = StructureAnalyzer()
        structure = analyzer.analyze(html)

        section_tags = [s["tag"] for s in structure.sections]
        assert "header" in section_tags
        assert "nav" in section_tags
        assert "main" in section_tags
        assert "article" in section_tags
        assert "aside" in section_tags
        assert "footer" in section_tags

    def test_extract_navigation(self):
        """Test extracting navigation links."""
        html = """
        <html>
        <body>
            <nav>
                <a href="/home">Home</a>
                <a href="/about">About</a>
                <a href="/contact">Contact</a>
            </nav>
        </body>
        </html>
        """
        analyzer = StructureAnalyzer()
        structure = analyzer.analyze(html, url="https://example.com")

        assert len(structure.navigation) == 3
        urls = [n["url"] for n in structure.navigation]
        assert "https://example.com/home" in urls
        assert "https://example.com/about" in urls

    def test_categorize_internal_external_links(self):
        """Test categorizing links as internal or external."""
        html = """
        <html>
        <body>
            <a href="/page1">Internal 1</a>
            <a href="https://example.com/page2">Internal 2</a>
            <a href="https://external.com">External</a>
        </body>
        </html>
        """
        analyzer = StructureAnalyzer()
        structure = analyzer.analyze(html, url="https://example.com")

        # Internal links
        internal_urls = [link["url"] for link in structure.internal_links]
        assert "https://example.com/page1" in internal_urls
        assert "https://example.com/page2" in internal_urls

        # External links
        external_urls = [link["url"] for link in structure.external_links]
        assert "https://external.com" in external_urls

    def test_find_forms(self):
        """Test finding forms."""
        html = """
        <html>
        <body>
            <form id="login-form" action="/login" method="POST">
                <input type="text" name="username" required>
                <input type="password" name="password" required>
                <button type="submit">Login</button>
            </form>
        </body>
        </html>
        """
        analyzer = StructureAnalyzer()
        structure = analyzer.analyze(html)

        assert len(structure.forms) == 1
        form = structure.forms[0]
        assert form["id"] == "login-form"
        assert form["action"] == "/login"
        assert form["method"] == "POST"
        assert len(form["fields"]) >= 2

    def test_build_outline(self):
        """Test building document outline."""
        html = """
        <html>
        <body>
            <h1>Main Title</h1>
            <h2>Section 1</h2>
            <p>Content</p>
            <h3>Subsection 1.1</h3>
            <h2>Section 2</h2>
        </body>
        </html>
        """
        analyzer = StructureAnalyzer()
        structure = analyzer.analyze(html)

        assert len(structure.outline) == 4
        assert structure.outline[0]["level"] == 1
        assert structure.outline[0]["text"] == "Main Title"
        assert structure.outline[1]["level"] == 2
        assert structure.outline[1]["text"] == "Section 1"

    def test_extract_meta(self):
        """Test extracting metadata."""
        html = """
        <html>
        <head>
            <meta name="description" content="Test description">
            <meta name="author" content="Test Author">
        </head>
        <body></body>
        </html>
        """
        analyzer = StructureAnalyzer()
        structure = analyzer.analyze(html)

        assert structure.meta["description"] == "Test description"
        assert structure.meta["author"] == "Test Author"

    def test_section_heading_extraction(self):
        """Test extracting section headings."""
        html = """
        <html>
        <body>
            <section id="intro">
                <h2>Introduction</h2>
                <p>Content</p>
            </section>
        </body>
        </html>
        """
        analyzer = StructureAnalyzer()
        structure = analyzer.analyze(html)

        section = next(s for s in structure.sections if s["id"] == "intro")
        assert section["heading"] == "Introduction"


class TestGetStructureMCPTool:
    """Integration tests for get_structure MCP tool."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()

    def teardown_method(self):
        """Reset state after each test."""
        reset_scraping_state()

    @pytest.mark.asyncio
    async def test_get_structure_basic(self, html_fixture_server):
        """Test basic structure analysis."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_structure", {"url": url})

        data = get_mcp_result_data(result)

        assert "error" not in data
        assert data["url"] == url
        assert data["title"] is not None
        assert "sections" in data

    @pytest.mark.asyncio
    async def test_get_structure_has_navigation(self, html_fixture_server):
        """Test that navigation links are extracted."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_structure", {"url": url})

        data = get_mcp_result_data(result)
        assert "navigation" in data
        # The fixture has nav links
        assert len(data["navigation"]) > 0

    @pytest.mark.asyncio
    async def test_get_structure_categorizes_links(self, html_fixture_server):
        """Test that links are categorized."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("external-links.html")
        result = await handle_call_tool("get_structure", {"url": url})

        data = get_mcp_result_data(result)
        assert "internal_links" in data
        assert "external_links" in data
        # external-links.html has both internal and external links
        assert len(data["external_links"]) > 0

    @pytest.mark.asyncio
    async def test_get_structure_finds_forms(self, html_fixture_server):
        """Test that forms are found."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("contact.html")
        result = await handle_call_tool("get_structure", {"url": url})

        data = get_mcp_result_data(result)
        assert "forms" in data
        # contact.html has a form
        assert len(data["forms"]) > 0

    @pytest.mark.asyncio
    async def test_get_structure_builds_outline(self, html_fixture_server):
        """Test that document outline is built."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("product-detail.html")
        result = await handle_call_tool("get_structure", {"url": url})

        data = get_mcp_result_data(result)
        assert "outline" in data
        assert len(data["outline"]) > 0

    @pytest.mark.asyncio
    async def test_get_structure_exclude_navigation(self, html_fixture_server):
        """Test excluding navigation from response."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool(
            "get_structure",
            {"url": url, "include_navigation": False},
        )

        data = get_mcp_result_data(result)
        assert data.get("navigation") is None

    @pytest.mark.asyncio
    async def test_get_structure_exclude_forms(self, html_fixture_server):
        """Test excluding forms from response."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("contact.html")
        result = await handle_call_tool(
            "get_structure",
            {"url": url, "include_forms": False},
        )

        data = get_mcp_result_data(result)
        assert data.get("forms") is None

    @pytest.mark.asyncio
    async def test_get_structure_chinese_page(self, html_fixture_server):
        """Test analyzing Chinese page."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("chinese.html")
        result = await handle_call_tool("get_structure", {"url": url})

        data = get_mcp_result_data(result)
        assert data.get("language") == "zh-CN"

    @pytest.mark.asyncio
    async def test_get_structure_japanese_page(self, html_fixture_server):
        """Test analyzing Japanese page."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("japanese.html")
        result = await handle_call_tool("get_structure", {"url": url})

        data = get_mcp_result_data(result)
        assert data.get("language") == "ja"

    @pytest.mark.asyncio
    async def test_get_structure_missing_url(self):
        """Test error when URL is missing."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool("get_structure", {})

        data = get_mcp_result_data(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_structure_404(self, html_fixture_server):
        """Test handling 404 response."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("nonexistent.html")
        result = await handle_call_tool("get_structure", {"url": url})

        data = get_mcp_result_data(result)
        assert "error" in data
        assert data.get("status_code") == 404

    @pytest.mark.asyncio
    async def test_tool_is_listed(self):
        """Test that get_structure tool is listed."""
        from app.mcp_server.mcp_server import handle_list_tools

        tools = await handle_list_tools()  # type: ignore[call-arg]
        tool_names = [t.name for t in tools]

        assert "get_structure" in tool_names

    @pytest.mark.asyncio
    async def test_tool_requires_url(self):
        """Test that tool schema requires url."""
        from app.mcp_server.mcp_server import handle_list_tools

        tools = await handle_list_tools()  # type: ignore[call-arg]
        tool = next(t for t in tools if t.name == "get_structure")

        assert "url" in tool.inputSchema.get("required", [])
