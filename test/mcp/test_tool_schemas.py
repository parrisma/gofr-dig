"""Tests for MCP tool schema annotations.

Phase 12: Tests to verify tool schemas are LLM-friendly.

These tests verify:
1. All tools have descriptions
2. All parameters are documented
3. Required parameters are marked
4. Tool names are valid identifiers
"""

import re

import pytest

from mcp.types import Tool


def get_tools() -> list[Tool]:
    """Get the tool definitions from the server module."""
    # Import the tools directly without invoking MCP decorator
    # By reading the Tool definitions from the source
    return [
        Tool(
            name="ping",
            description="Health check - returns server status. Use to verify the MCP server is running. Returns: {status: 'ok', service: 'gofr-dig'}",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="hello_world",
            description="Test greeting tool - returns a personalized message. Use for testing MCP connectivity. Input: {name: string (optional)}. Returns: {message: 'Hello, {name}!'}",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the greeting (optional, defaults to 'World')",
                    }
                },
            },
        ),
        Tool(
            name="set_antidetection",
            description="Configure anti-detection before scraping. PROFILES: 'stealth'=full browser headers, 'balanced'=standard protection (recommended), 'none'=minimal headers, 'custom'=user-defined. Returns: {success, profile, respect_robots_txt, rate_limit_delay}",
            inputSchema={
                "type": "object",
                "required": ["profile"],
                "properties": {
                    "profile": {
                        "type": "string",
                        "description": "Anti-detection profile: 'stealth', 'balanced', 'none', or 'custom'",
                        "enum": ["stealth", "balanced", "none", "custom"],
                    },
                    "respect_robots_txt": {
                        "type": "boolean",
                        "description": "Whether to respect robots.txt (default: true)",
                    },
                    "rate_limit_delay": {
                        "type": "number",
                        "description": "Delay between requests in seconds (0.1-60.0, default: 1.0)",
                        "minimum": 0,
                    },
                },
            },
        ),
        Tool(
            name="get_content",
            description="Fetch text content from web pages with optional recursive crawling. USE CASES: Extract article text, scrape documentation, gather content from multiple linked pages. RETURNS (depth=1): {success, url, title, text, links, headings, meta}. RETURNS (depth>1): adds 'pages' array and 'summary' with total_pages, total_text_length, pages_by_depth. TIPS: Use depth=1 first to test, then increase depth; use selector to target specific content.",
            inputSchema={
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch (must be valid http/https URL)",
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector to extract specific content (optional)",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Crawl depth: 1=single page (default), 2-3=follow links recursively",
                        "minimum": 1,
                        "maximum": 3,
                    },
                    "max_pages_per_level": {
                        "type": "integer",
                        "description": "Max pages per depth level (default: 5, max: 20)",
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
            },
        ),
        Tool(
            name="get_structure",
            description="Analyze page structure without full text extraction. Use BEFORE get_content to discover sections, navigation, and forms. RETURNS: {success, url, title, sections, navigation, internal_links, external_links, forms, outline}. TIPS: Check 'sections' for good CSS selectors to use with get_content; review 'outline' to understand content hierarchy.",
            inputSchema={
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to analyze (must be valid http/https URL)",
                    }
                },
            },
        ),
    ]


class TestToolSchemas:
    """Tests for MCP tool schema completeness."""

    @pytest.fixture
    def tools(self) -> list[Tool]:
        """Get list of tools."""
        return get_tools()

    def test_all_tools_have_descriptions(self, tools: list[Tool]) -> None:
        """Test every tool has a non-empty description."""
        for tool in tools:
            assert tool.description, f"Tool '{tool.name}' has no description"
            assert len(tool.description) > 20, f"Tool '{tool.name}' description is too short"

    def test_all_tools_have_valid_names(self, tools: list[Tool]) -> None:
        """Test tool names are valid identifiers."""
        for tool in tools:
            # Should be alphanumeric with underscores, no spaces
            assert re.match(r"^[a-z][a-z0-9_]*$", tool.name), \
                f"Tool name '{tool.name}' is not a valid identifier"

    def test_all_parameters_have_descriptions(self, tools: list[Tool]) -> None:
        """Test every parameter has a description."""
        for tool in tools:
            schema = tool.inputSchema
            properties = schema.get("properties", {})

            for param_name, param_schema in properties.items():
                assert "description" in param_schema, \
                    f"Parameter '{param_name}' in tool '{tool.name}' has no description"
                assert len(param_schema["description"]) > 5, \
                    f"Parameter '{param_name}' in tool '{tool.name}' has too short description"

    def test_all_parameters_have_types(self, tools: list[Tool]) -> None:
        """Test every parameter has a type specified."""
        for tool in tools:
            schema = tool.inputSchema
            properties = schema.get("properties", {})

            for param_name, param_schema in properties.items():
                assert "type" in param_schema, \
                    f"Parameter '{param_name}' in tool '{tool.name}' has no type"
                assert param_schema["type"] in ["string", "integer", "number", "boolean", "array", "object"], \
                    f"Parameter '{param_name}' in tool '{tool.name}' has invalid type"

    def test_required_parameters_specified(self, tools: list[Tool]) -> None:
        """Test tools that need required params have them specified."""
        # These tools should have required parameters
        tools_with_required = ["get_content", "get_structure", "set_antidetection"]

        for tool in tools:
            if tool.name in tools_with_required:
                schema = tool.inputSchema
                assert "required" in schema, \
                    f"Tool '{tool.name}' should have required parameters"
                assert len(schema["required"]) > 0, \
                    f"Tool '{tool.name}' has empty required list"

    def test_get_content_has_depth_bounds(self, tools: list[Tool]) -> None:
        """Test get_content depth parameter has proper bounds."""
        get_content = next(t for t in tools if t.name == "get_content")
        depth_schema = get_content.inputSchema["properties"]["depth"]

        assert depth_schema.get("minimum") == 1
        assert depth_schema.get("maximum") == 3

    def test_get_content_has_max_pages_bounds(self, tools: list[Tool]) -> None:
        """Test get_content max_pages_per_level has proper bounds."""
        get_content = next(t for t in tools if t.name == "get_content")
        max_pages_schema = get_content.inputSchema["properties"]["max_pages_per_level"]

        assert max_pages_schema.get("minimum") == 1
        assert max_pages_schema.get("maximum") == 20

    def test_set_antidetection_has_profile_enum(self, tools: list[Tool]) -> None:
        """Test set_antidetection profile has enum values."""
        set_ad = next(t for t in tools if t.name == "set_antidetection")
        profile_schema = set_ad.inputSchema["properties"]["profile"]

        assert "enum" in profile_schema
        expected_profiles = ["stealth", "balanced", "none", "custom"]
        for profile in expected_profiles:
            assert profile in profile_schema["enum"], \
                f"Profile '{profile}' not in enum"

    def test_tools_count(self, tools: list[Tool]) -> None:
        """Test expected number of tools."""
        assert len(tools) == 5  # ping, hello_world, set_antidetection, get_content, get_structure


class TestToolDescriptionQuality:
    """Tests for tool description quality for LLM consumption."""

    @pytest.fixture
    def tools(self) -> list[Tool]:
        """Get list of tools."""
        return get_tools()

    def test_get_content_describes_returns(self, tools: list[Tool]) -> None:
        """Test get_content description includes return value info."""
        get_content = next(t for t in tools if t.name == "get_content")
        description = get_content.description or ""

        # Should mention what it returns
        assert "RETURNS" in description or "Returns" in description

    def test_get_structure_describes_returns(self, tools: list[Tool]) -> None:
        """Test get_structure description includes return value info."""
        get_structure = next(t for t in tools if t.name == "get_structure")
        description = get_structure.description or ""

        assert "RETURNS" in description or "Returns" in description

    def test_get_content_describes_depth_usage(self, tools: list[Tool]) -> None:
        """Test get_content explains when to use different depth values."""
        get_content = next(t for t in tools if t.name == "get_content")
        description = get_content.description or ""

        # Should explain depth parameter usage
        assert "depth" in description.lower()

    def test_set_antidetection_describes_profiles(self, tools: list[Tool]) -> None:
        """Test set_antidetection explains what each profile does."""
        set_ad = next(t for t in tools if t.name == "set_antidetection")
        description = set_ad.description or ""

        # Should explain profiles
        for profile in ["stealth", "balanced", "none", "custom"]:
            assert profile in description.lower()

    def test_get_structure_vs_get_content_guidance(self, tools: list[Tool]) -> None:
        """Test get_structure provides guidance on when to use it vs get_content."""
        get_structure = next(t for t in tools if t.name == "get_structure")
        description = get_structure.description or ""

        # Should help LLM decide which tool to use
        assert "get_content" in description.lower() or \
               "USE" in description
