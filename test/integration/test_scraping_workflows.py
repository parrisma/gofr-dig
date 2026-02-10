"""Integration tests for scraping toolkit workflows.

These tests simulate realistic LLM-agent workflows that combine
multiple tools together to accomplish common tasks.

Note: These tests use the html_fixture_server fixture from conftest.py
and create MCP sessions inline for each test.
"""

import json
import os
import pytest
from mcp import ClientSession
from mcp.client import streamable_http

streamable_http_client = streamable_http.streamablehttp_client


# Service URL — prefer full URL env var (set by run_tests.sh --docker/--no-docker),
# fall back to host+port construction (env vars set by gofr_ports.env).
MCP_URL = os.environ.get(
    "GOFR_DIG_MCP_URL",
    "http://{}:{}/mcp".format(
        os.environ.get("GOFR_DIG_HOST", "localhost"),
        os.environ["GOFR_DIG_MCP_PORT_TEST"],
    ),
)


def parse_json(result) -> dict:
    """Parse JSON from MCP result.
    
    If the result is not JSON (e.g., validation error), return a dict
    with success=False and the error message.
    """
    if result.content and len(result.content) > 0:
        text = result.content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Not JSON - likely an error message
            return {"success": False, "error": text}
    return {"success": False, "error": "Empty response"}


class TestWebResearchWorkflow:
    """Test: LLM agent researching a website for information."""

    @pytest.mark.asyncio
    async def test_research_workflow_structure_then_content(self, html_fixture_server):
        """
        Workflow: Agent explores site structure, then extracts specific content.

        This simulates an LLM:
        1. First getting the site structure to understand what's available
        2. Then extracting specific content from interesting pages
        """
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Step 1: Get site structure to understand available pages
                structure_result = await session.call_tool(
                    "get_structure", {"url": f"{base_url}/index.html"}
                )
                structure = parse_json(structure_result)

                assert structure["success"] is True

                # Verify we can see navigation links
                nav_links = structure.get("navigation", [])
                assert len(nav_links) > 0, "Should find navigation links"

                # Step 2: Get content from products page
                content_result = await session.call_tool(
                    "get_content", {"url": f"{base_url}/products.html"}
                )
                content = parse_json(content_result)

                assert content["success"] is True
                assert "products" in content["title"].lower()
                assert len(content["text"]) > 100

    @pytest.mark.asyncio
    async def test_research_workflow_with_antidetection(self, html_fixture_server):
        """
        Workflow: Agent configures stealth mode before scraping.

        This simulates an LLM being cautious about detection:
        1. Enable stealth anti-detection profile
        2. Perform scraping operations
        """
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Step 1: Configure stealth anti-detection
                antidetect_result = await session.call_tool(
                    "set_antidetection", {"profile": "stealth"}
                )
                antidetect = parse_json(antidetect_result)

                assert antidetect["success"] is True
                assert antidetect["profile"] == "stealth"

                # Step 2: Now fetch content with stealth settings active
                content_result = await session.call_tool(
                    "get_content", {"url": f"{base_url}/products.html"}
                )
                content = parse_json(content_result)

                assert content["success"] is True

    @pytest.mark.asyncio
    async def test_research_workflow_selector_targeting(self, html_fixture_server):
        """
        Workflow: Agent uses selectors to extract specific data.

        This simulates an LLM:
        1. First exploring page structure
        2. Then using CSS selectors to extract specific elements
        """
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Step 1: Get structure to understand page layout
                structure_result = await session.call_tool(
                    "get_structure", {"url": f"{base_url}/products.html"}
                )
                structure = parse_json(structure_result)
                assert structure["success"] is True

                # Step 2: Use selector to get specific content
                content_result = await session.call_tool(
                    "get_content",
                    {"url": f"{base_url}/products.html", "selector": ".product-card"},
                )
                content = parse_json(content_result)
                assert content["success"] is True


class TestMultiLanguageWorkflow:
    """Test: LLM agent processing multilingual content."""

    @pytest.mark.asyncio
    async def test_chinese_content_extraction(self, html_fixture_server):
        """Workflow: Extract and process Chinese content."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Get structure first
                structure_result = await session.call_tool(
                    "get_structure", {"url": f"{base_url}/chinese.html"}
                )
                structure = parse_json(structure_result)

                assert structure["success"] is True
                # Language may be "zh" or "zh-CN"
                assert structure["language"].startswith("zh")

                # Get content
                content_result = await session.call_tool(
                    "get_content", {"url": f"{base_url}/chinese.html"}
                )
                content = parse_json(content_result)

                assert content["success"] is True
                assert content["language"].startswith("zh")
                # Should contain Chinese characters
                assert "中" in content["text"] or "文" in content["text"]

    @pytest.mark.asyncio
    async def test_japanese_content_extraction(self, html_fixture_server):
        """Workflow: Extract and process Japanese content."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                content_result = await session.call_tool(
                    "get_content", {"url": f"{base_url}/japanese.html"}
                )
                content = parse_json(content_result)

                assert content["success"] is True
                assert content["language"] == "ja"
                # Should contain Japanese characters
                text = content["text"]
                assert any(char in text for char in ["日", "本", "語", "の", "は"])


class TestRobotsComplianceWorkflow:
    """Test: LLM agent respecting robots.txt rules."""

    @pytest.mark.asyncio
    async def test_robots_blocks_admin_pages(self, html_fixture_server):
        """Workflow: Agent attempts to access blocked path."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Ensure robots.txt compliance is enabled (default)
                antidetect_result = await session.call_tool(
                    "set_antidetection", {"profile": "balanced", "respect_robots_txt": True}
                )
                antidetect = parse_json(antidetect_result)
                assert antidetect["respect_robots_txt"] is True

                # Try to access /admin/ path (blocked by robots.txt)
                content_result = await session.call_tool(
                    "get_content", {"url": f"{base_url}/admin/secret.html"}
                )
                content = parse_json(content_result)

                # Should be blocked by robots.txt
                assert content.get("robots_blocked") is True or content.get("success") is False

    @pytest.mark.asyncio
    async def test_robots_allows_public_pages(self, html_fixture_server):
        """Workflow: Agent accesses allowed paths."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Access public pages (allowed)
                content_result = await session.call_tool(
                    "get_content", {"url": f"{base_url}/products.html"}
                )
                content = parse_json(content_result)

                assert content["success"] is True
                assert content.get("robots_blocked") is not True

    @pytest.mark.asyncio
    async def test_disable_robots_compliance(self, html_fixture_server):
        """Workflow: Agent disables robots.txt checking for special access."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Disable robots.txt compliance
                antidetect_result = await session.call_tool(
                    "set_antidetection", {"profile": "none", "respect_robots_txt": False}
                )
                antidetect = parse_json(antidetect_result)
                assert antidetect["respect_robots_txt"] is False

                # Now /admin/ should not be blocked (though may 404)
                content_result = await session.call_tool(
                    "get_content", {"url": f"{base_url}/admin/page.html"}
                )
                content = parse_json(content_result)

                # Should NOT be robots_blocked (may fail for other reasons like 404)
                assert content.get("robots_blocked") is not True


class TestLinkDiscoveryWorkflow:
    """Test: LLM agent discovering and following links."""

    @pytest.mark.asyncio
    async def test_discover_internal_links(self, html_fixture_server):
        """Workflow: Agent discovers all internal links on a page."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                structure_result = await session.call_tool(
                    "get_structure", {"url": f"{base_url}/index.html"}
                )
                structure = parse_json(structure_result)

                assert structure["success"] is True

                # Should have internal links
                assert "internal_links" in structure
                assert len(structure["internal_links"]) > 0

    @pytest.mark.asyncio
    async def test_discover_external_links(self, html_fixture_server):
        """Workflow: Agent identifies external links."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                structure_result = await session.call_tool(
                    "get_structure", {"url": f"{base_url}/external-links.html"}
                )
                structure = parse_json(structure_result)

                assert structure["success"] is True

                # Should have external links
                assert "external_links" in structure
                assert len(structure["external_links"]) > 0

    @pytest.mark.asyncio
    async def test_crawl_blog_structure(self, html_fixture_server):
        """Workflow: Agent explores blog directory structure."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Get blog index structure
                structure_result = await session.call_tool(
                    "get_structure", {"url": f"{base_url}/blog/index.html"}
                )
                structure = parse_json(structure_result)

                assert structure["success"] is True

                # Should have outline with blog posts
                outline = structure.get("outline", [])
                assert len(outline) > 0, "Blog should have heading structure"


class TestErrorHandlingWorkflow:
    """Test: LLM agent handling errors gracefully."""

    @pytest.mark.asyncio
    async def test_handle_404_gracefully(self, html_fixture_server):
        """Workflow: Agent handles missing pages."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                content_result = await session.call_tool(
                    "get_content", {"url": f"{base_url}/nonexistent-page.html"}
                )
                content = parse_json(content_result)

                # Should fail gracefully with error info
                assert content["success"] is False
                assert "error" in content

    @pytest.mark.asyncio
    async def test_handle_invalid_selector(self, html_fixture_server):
        """Workflow: Agent handles invalid CSS selectors."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                content_result = await session.call_tool(
                    "get_content",
                    {"url": f"{base_url}/index.html", "selector": "[[[invalid"},
                )
                content = parse_json(content_result)

                # Should fail gracefully
                assert content["success"] is False
                assert "error" in content

    @pytest.mark.asyncio
    async def test_handle_missing_url(self):
        """Workflow: Agent forgets to provide URL."""
        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                content_result = await session.call_tool("get_content", {})
                content = parse_json(content_result)

                assert content["success"] is False
                assert "url" in content["error"].lower()


class TestFullScrapingPipeline:
    """Test: Complete end-to-end scraping pipeline."""

    @pytest.mark.asyncio
    async def test_complete_research_pipeline(self, html_fixture_server):
        """
        Full pipeline test simulating an LLM research task:

        1. Configure anti-detection
        2. Get site structure
        3. Extract content from multiple pages
        4. Handle errors gracefully
        """
        base_url = html_fixture_server.base_url
        results = {"pages_analyzed": 0, "total_content_length": 0, "errors": []}

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Step 1: Configure anti-detection
                await session.call_tool(
                    "set_antidetection", {"profile": "balanced", "respect_robots_txt": True}
                )

                # Step 2: Get homepage structure
                structure_result = await session.call_tool(
                    "get_structure", {"url": f"{base_url}/index.html"}
                )
                structure = parse_json(structure_result)
                assert structure["success"] is True

                # Step 3: Extract content from multiple pages
                pages_to_analyze = [
                    "/index.html",
                    "/products.html",
                    "/about.html",
                    "/contact.html",
                ]

                for page in pages_to_analyze:
                    try:
                        content_result = await session.call_tool(
                            "get_content", {"url": f"{base_url}{page}"}
                        )
                        content = parse_json(content_result)

                        if content.get("success"):
                            results["pages_analyzed"] += 1
                            results["total_content_length"] += len(
                                content.get("text", "")
                            )
                        else:
                            results["errors"].append(
                                {"page": page, "error": content.get("error")}
                            )
                    except Exception as e:
                        results["errors"].append({"page": page, "error": str(e)})

        # Verify pipeline success
        assert results["pages_analyzed"] >= 3, "Should analyze at least 3 pages"
        assert results["total_content_length"] > 500, "Should extract substantial content"

    @pytest.mark.asyncio
    async def test_multilingual_research_pipeline(self, html_fixture_server):
        """Pipeline test for multilingual content analysis."""
        base_url = html_fixture_server.base_url
        languages_found = set()

        pages = [
            "/index.html",
            "/chinese.html",
            "/japanese.html",
        ]

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                for page in pages:
                    content_result = await session.call_tool(
                        "get_content", {"url": f"{base_url}{page}"}
                    )
                    content = parse_json(content_result)

                    if content.get("success"):
                        lang = content.get("language")
                        if lang:
                            languages_found.add(lang)

        # Should detect multiple languages
        assert len(languages_found) >= 2, f"Should detect multiple languages, found: {languages_found}"


class TestAntiDetectionProfiles:
    """Test: Different anti-detection profile behaviors."""

    @pytest.mark.asyncio
    async def test_stealth_profile_settings(self):
        """Verify stealth profile configuration."""
        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "set_antidetection", {"profile": "stealth"}
                )
                config = parse_json(result)

                assert config["success"] is True
                assert config["profile"] == "stealth"
                assert config["status"] == "configured"
                # Stealth has longer delay and browser-like user agent
                assert "profile_info" in config

    @pytest.mark.asyncio
    async def test_balanced_profile_settings(self):
        """Verify balanced profile configuration."""
        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "set_antidetection", {"profile": "balanced"}
                )
                config = parse_json(result)

                assert config["success"] is True
                assert config["profile"] == "balanced"

    @pytest.mark.asyncio
    async def test_none_profile_settings(self):
        """Verify none profile disables anti-detection."""
        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "set_antidetection", {"profile": "none"}
                )
                config = parse_json(result)

                assert config["success"] is True
                assert config["profile"] == "none"

    @pytest.mark.asyncio
    async def test_custom_profile_settings(self):
        """Verify custom profile with specific settings."""
        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "set_antidetection",
                    {
                        "profile": "custom",
                        "rate_limit_delay": 2.0,
                        "respect_robots_txt": False,
                    },
                )
                config = parse_json(result)

                assert config["success"] is True
                assert config["profile"] == "custom"
                assert config["rate_limit_delay"] == 2.0
                assert config["respect_robots_txt"] is False


class TestContentExtractionOptions:
    """Test: Various content extraction options."""

    @pytest.mark.asyncio
    async def test_include_links_option(self, html_fixture_server):
        """Test including links in content extraction."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "get_content",
                    {"url": f"{base_url}/index.html", "include_links": True},
                )
                content = parse_json(result)

                assert content["success"] is True
                assert "links" in content
                assert len(content["links"]) > 0

    @pytest.mark.asyncio
    async def test_exclude_links_option(self, html_fixture_server):
        """Test excluding links from content extraction."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "get_content",
                    {"url": f"{base_url}/index.html", "include_links": False},
                )
                content = parse_json(result)

                assert content["success"] is True
                # Links should be empty or not present
                links = content.get("links", [])
                assert len(links) == 0

    @pytest.mark.asyncio
    async def test_include_images_option(self, html_fixture_server):
        """Test including images in content extraction."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "get_content",
                    {"url": f"{base_url}/products.html", "include_images": True},
                )
                content = parse_json(result)

                assert content["success"] is True
                assert "images" in content


class TestStructureAnalysisOptions:
    """Test: Various structure analysis options."""

    @pytest.mark.asyncio
    async def test_include_navigation(self, html_fixture_server):
        """Test navigation extraction in structure."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "get_structure",
                    {"url": f"{base_url}/index.html", "include_navigation": True},
                )
                structure = parse_json(result)

                assert structure["success"] is True
                assert "navigation" in structure

    @pytest.mark.asyncio
    async def test_include_forms(self, html_fixture_server):
        """Test form detection in structure."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "get_structure",
                    {"url": f"{base_url}/contact.html", "include_forms": True},
                )
                structure = parse_json(result)

                assert structure["success"] is True
                assert "forms" in structure

    @pytest.mark.asyncio
    async def test_outline_extraction(self, html_fixture_server):
        """Test heading outline extraction."""
        base_url = html_fixture_server.base_url

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "get_structure", {"url": f"{base_url}/index.html"}
                )
                structure = parse_json(result)

                assert structure["success"] is True
                assert "outline" in structure
                # Should have at least one heading
                assert len(structure["outline"]) > 0
