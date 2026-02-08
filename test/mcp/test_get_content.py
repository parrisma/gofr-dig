"""Tests for get_content MCP tool.

Tests the content extraction tool for web scraping.
"""

import json
from typing import Any, List

import pytest

from app.scraping.extractor import ContentExtractor
from app.scraping.state import reset_scraping_state


def get_mcp_result_data(result: Any) -> dict:
    """Extract JSON data from MCP tool result."""
    # Cast to list for type checking - MCP returns list of TextContent
    result_list: List[Any] = result  # type: ignore[assignment]
    return json.loads(result_list[0].text)  # type: ignore[union-attr]


class TestContentExtractor:
    """Tests for ContentExtractor class."""

    def test_extract_title(self):
        """Test extracting page title."""
        html = """
        <html>
        <head><title>Test Page Title</title></head>
        <body><h1>Main Heading</h1></body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html)

        assert content.success
        assert content.title == "Test Page Title"

    def test_extract_title_fallback_to_h1(self):
        """Test fallback to h1 when no title tag."""
        html = """
        <html>
        <body><h1>Fallback Heading</h1></body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html)

        assert content.title == "Fallback Heading"

    def test_extract_text(self):
        """Test extracting text content."""
        html = """
        <html>
        <body>
            <p>First paragraph.</p>
            <p>Second paragraph.</p>
        </body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html)

        assert "First paragraph" in content.text
        assert "Second paragraph" in content.text

    def test_removes_script_tags(self):
        """Test that script tags are removed."""
        html = """
        <html>
        <body>
            <p>Visible text</p>
            <script>var hidden = "should not appear";</script>
        </body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html)

        assert "Visible text" in content.text
        assert "should not appear" not in content.text

    def test_removes_style_tags(self):
        """Test that style tags are removed."""
        html = """
        <html>
        <body>
            <p>Visible text</p>
            <style>.hidden { display: none; }</style>
        </body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html)

        assert "Visible text" in content.text
        assert "display: none" not in content.text

    def test_extract_links(self):
        """Test extracting links."""
        html = """
        <html>
        <body>
            <a href="/page1">Internal Link</a>
            <a href="https://external.com">External Link</a>
        </body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html, url="https://example.com")

        assert len(content.links) == 2

        internal = next(link for link in content.links if "Internal" in link["text"])
        assert internal["url"] == "https://example.com/page1"
        assert internal["external"] is False

        external = next(link for link in content.links if "External" in link["text"])
        assert external["url"] == "https://external.com"
        assert external["external"] is True

    def test_extract_images(self):
        """Test extracting images."""
        html = """
        <html>
        <body>
            <img src="/img/photo.jpg" alt="A photo">
            <img src="https://cdn.example.com/logo.png" alt="Logo">
        </body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html, url="https://example.com")

        assert len(content.images) == 2
        assert any(i["alt"] == "A photo" for i in content.images)
        assert any("logo.png" in i["url"] for i in content.images)

    def test_extract_headings(self):
        """Test extracting headings."""
        html = """
        <html>
        <body>
            <h1>Main Title</h1>
            <h2>Section 1</h2>
            <h3>Subsection 1.1</h3>
            <h2>Section 2</h2>
        </body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html)

        assert len(content.headings) == 4
        assert content.headings[0] == {"level": 1, "text": "Main Title"}
        assert content.headings[1] == {"level": 2, "text": "Section 1"}

    def test_extract_meta(self):
        """Test extracting metadata."""
        html = """
        <html>
        <head>
            <meta name="description" content="Page description">
            <meta name="keywords" content="test, extraction">
            <meta property="og:title" content="OG Title">
        </head>
        <body></body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html)

        assert content.meta["description"] == "Page description"
        assert content.meta["keywords"] == "test, extraction"
        assert content.meta["og:title"] == "OG Title"

    def test_extract_language(self):
        """Test extracting language."""
        html = """
        <html lang="zh-CN">
        <body><p>Chinese content</p></body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html)

        assert content.language == "zh-CN"

    def test_extract_with_selector(self):
        """Test extraction with CSS selector."""
        html = """
        <html>
        <body>
            <div id="sidebar">Sidebar content</div>
            <main id="content">
                <p>Main content here</p>
            </main>
        </body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract_by_selector(html, "#content")

        assert "Main content" in content.text
        assert "Sidebar" not in content.text

    def test_invalid_selector_returns_error(self):
        """Test that invalid selector returns error."""
        html = "<html><body><p>Text</p></body></html>"
        extractor = ContentExtractor()
        content = extractor.extract_by_selector(html, "#nonexistent")

        assert not content.success
        assert content.error is not None and "did not match" in content.error

    def test_extract_chinese_content(self):
        """Test extracting Chinese content."""
        html = """
        <html lang="zh-CN">
        <head><title>欢迎访问</title></head>
        <body><p>ACME公司是全球领先的科技解决方案提供商。</p></body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html)

        assert content.title == "欢迎访问"
        assert "全球领先" in content.text

    def test_extract_japanese_content(self):
        """Test extracting Japanese content."""
        html = """
        <html lang="ja">
        <head><title>ようこそ</title></head>
        <body><p>ACME株式会社は世界をリードするテクノロジーソリューションプロバイダーです。</p></body>
        </html>
        """
        extractor = ContentExtractor()
        content = extractor.extract(html)

        assert content.title == "ようこそ"
        assert "テクノロジー" in content.text


class TestGetContentMCPTool:
    """Integration tests for get_content MCP tool."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()

    def teardown_method(self):
        """Reset state after each test."""
        reset_scraping_state()

    @pytest.mark.asyncio
    async def test_get_content_basic(self, html_fixture_server):
        """Test basic content extraction."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool("get_content", {"url": url})

        data = get_mcp_result_data(result)

        assert "error" not in data
        assert "ACME" in data["title"] or "ACME" in data["text"]
        assert data["url"] == url

    @pytest.mark.asyncio
    async def test_get_content_products_page(self, html_fixture_server):
        """Test extracting products page."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("products.html")
        result = await handle_call_tool("get_content", {"url": url})

        data = get_mcp_result_data(result)
        assert "Widget Pro 3000" in data["text"]
        assert "Gadget Plus" in data["text"]

    @pytest.mark.asyncio
    async def test_get_content_with_selector(self, html_fixture_server):
        """Test content extraction with CSS selector."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool(
            "get_content",
            {"url": url, "selector": "#content"},
        )

        data = get_mcp_result_data(result)
        assert "error" not in data
        assert len(data["text"]) > 0

    @pytest.mark.asyncio
    async def test_get_content_includes_links(self, html_fixture_server):
        """Test that links are included by default."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("external-links.html")
        result = await handle_call_tool("get_content", {"url": url})

        data = get_mcp_result_data(result)
        assert "links" in data
        assert len(data["links"]) > 0

    @pytest.mark.asyncio
    async def test_get_content_exclude_links(self, html_fixture_server):
        """Test excluding links from extraction."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("index.html")
        result = await handle_call_tool(
            "get_content",
            {"url": url, "include_links": False},
        )

        data = get_mcp_result_data(result)
        # Links might still be present but empty
        assert data.get("links") is None or len(data.get("links", [])) == 0

    @pytest.mark.asyncio
    async def test_get_content_include_images(self, html_fixture_server):
        """Test including images in extraction."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("product-detail.html")
        result = await handle_call_tool(
            "get_content",
            {"url": url, "include_images": True},
        )

        data = get_mcp_result_data(result)
        # Images may or may not be present depending on HTML
        assert "error" not in data

    @pytest.mark.asyncio
    async def test_get_content_chinese(self, html_fixture_server):
        """Test extracting Chinese content."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("chinese.html")
        result = await handle_call_tool("get_content", {"url": url})

        data = get_mcp_result_data(result)
        assert "欢迎" in data.get("title", "") or "欢迎" in data["text"]
        assert data.get("language") == "zh-CN"

    @pytest.mark.asyncio
    async def test_get_content_japanese(self, html_fixture_server):
        """Test extracting Japanese content."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("japanese.html")
        result = await handle_call_tool("get_content", {"url": url})

        data = get_mcp_result_data(result)
        assert "ようこそ" in data.get("title", "") or "ようこそ" in data["text"]
        assert data.get("language") == "ja"

    @pytest.mark.asyncio
    async def test_get_content_missing_url(self):
        """Test error when URL is missing."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool("get_content", {})

        data = get_mcp_result_data(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_content_invalid_url(self):
        """Test error for invalid URL."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool(
            "get_content",
            {"url": "not-a-valid-url"},
        )

        data = get_mcp_result_data(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_content_404(self, html_fixture_server):
        """Test handling 404 response."""
        from app.mcp_server.mcp_server import handle_call_tool

        url = html_fixture_server.get_url("nonexistent.html")
        result = await handle_call_tool("get_content", {"url": url})

        data = get_mcp_result_data(result)
        assert "error" in data
        assert data.get("error_code") == "URL_NOT_FOUND"
        assert data.get("status_code") == 404

    @pytest.mark.asyncio
    async def test_tool_is_listed(self):
        """Test that get_content tool is listed."""
        from app.mcp_server.mcp_server import handle_list_tools

        tools = await handle_list_tools()  # type: ignore[call-arg]
        tool_names = [t.name for t in tools]

        assert "get_content" in tool_names

    @pytest.mark.asyncio
    async def test_tool_requires_url(self):
        """Test that tool schema requires url."""
        from app.mcp_server.mcp_server import handle_list_tools

        tools = await handle_list_tools()  # type: ignore[call-arg]
        tool = next(t for t in tools if t.name == "get_content")

        assert "url" in tool.inputSchema.get("required", [])
