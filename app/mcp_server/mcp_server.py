#!/usr/bin/env python3
"""GOFR-DIG MCP Server - Hello World Implementation."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, AsyncIterator, Dict, List

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool

from app.logger import session_logger as logger
from app.scraping import (
    AntiDetectionManager,
    AntiDetectionProfile,
    fetch_url,
)
from app.scraping.state import get_scraping_state

# Module-level configuration (set by main_mcp.py)
auth_service: Any = None
templates_dir_override: str | None = None
styles_dir_override: str | None = None
web_url_override: str | None = None
proxy_url_mode: bool = False

app = Server("gofr-dig-service")


def _json_text(data: Dict[str, Any]) -> TextContent:
    """Create JSON text content."""
    return TextContent(type="text", text=json.dumps(data, indent=2))


@app.list_tools()
async def handle_list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="ping",
            description="Health check - returns server status",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="hello_world",
            description="Returns a greeting message",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Optional name to greet",
                    }
                },
            },
        ),
        Tool(
            name="set_antidetection",
            description="Configure anti-detection settings for web scraping. Settings persist for the session.",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "string",
                        "enum": ["stealth", "balanced", "none", "custom"],
                        "description": "Anti-detection profile: 'stealth' (max protection), 'balanced' (default), 'none' (minimal headers), 'custom' (user-defined)",
                    },
                    "custom_headers": {
                        "type": "object",
                        "description": "Custom headers to use when profile is 'custom'. Keys are header names, values are header values.",
                        "additionalProperties": {"type": "string"},
                    },
                    "custom_user_agent": {
                        "type": "string",
                        "description": "Custom User-Agent string when profile is 'custom'",
                    },
                    "respect_robots_txt": {
                        "type": "boolean",
                        "description": "Whether to respect robots.txt rules (default: true)",
                    },
                    "rate_limit_delay": {
                        "type": "number",
                        "description": "Delay in seconds between requests (default: 1.0)",
                        "minimum": 0,
                    },
                },
                "required": ["profile"],
            },
        ),
        Tool(
            name="get_content",
            description="Fetch a web page and extract its text content. Supports recursive crawling with depth parameter. Uses configured anti-detection settings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch and extract content from",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Crawl depth: 1=single page (default), 2=follow internal links one level, 3=follow two levels. Max 3.",
                        "minimum": 1,
                        "maximum": 3,
                        "default": 1,
                    },
                    "max_pages_per_level": {
                        "type": "integer",
                        "description": "Maximum pages to fetch per depth level (default: 5). Helps control crawl scope.",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 5,
                    },
                    "selector": {
                        "type": "string",
                        "description": "Optional CSS selector to limit extraction to specific elements",
                    },
                    "include_links": {
                        "type": "boolean",
                        "description": "Include links found in the content (default: true)",
                    },
                    "include_images": {
                        "type": "boolean",
                        "description": "Include images found in the content (default: false)",
                    },
                    "include_meta": {
                        "type": "boolean",
                        "description": "Include page metadata (default: true)",
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="get_structure",
            description="Analyze the structure of a web page. Returns semantic sections, navigation, links, forms, and document outline.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to analyze",
                    },
                    "include_navigation": {
                        "type": "boolean",
                        "description": "Include navigation links (default: true)",
                    },
                    "include_internal_links": {
                        "type": "boolean",
                        "description": "Include internal links (default: true)",
                    },
                    "include_external_links": {
                        "type": "boolean",
                        "description": "Include external links (default: true)",
                    },
                    "include_forms": {
                        "type": "boolean",
                        "description": "Include form analysis (default: true)",
                    },
                    "include_outline": {
                        "type": "boolean",
                        "description": "Include document outline/headings (default: true)",
                    },
                },
                "required": ["url"],
            },
        ),
    ]


@app.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool invocations."""
    logger.info("Tool called", tool=name, args=arguments)

    if name == "ping":
        return [_json_text({"status": "ok", "service": "gofr-dig"})]

    if name == "hello_world":
        greeting_name = arguments.get("name", "World")
        return [_json_text({"message": f"Hello, {greeting_name}!"})]

    if name == "set_antidetection":
        return await _handle_set_antidetection(arguments)

    if name == "get_content":
        return await _handle_get_content(arguments)

    if name == "get_structure":
        return await _handle_get_structure(arguments)

    return [_json_text({"error": f"Unknown tool: {name}"})]


async def _handle_set_antidetection(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle the set_antidetection tool.

    Configures anti-detection settings for web scraping operations.
    Settings persist in the global scraping state.
    """
    profile_str = arguments.get("profile", "balanced")

    # Validate and convert profile
    try:
        profile = AntiDetectionProfile(profile_str)
    except ValueError:
        valid_profiles = [p.value for p in AntiDetectionProfile]
        return [
            _json_text(
                {
                    "error": f"Invalid profile: {profile_str}",
                    "valid_profiles": valid_profiles,
                }
            )
        ]

    # Get the global scraping state
    state = get_scraping_state()

    # Update the state
    state.antidetection_profile = profile
    state.custom_headers = arguments.get("custom_headers", {})
    state.custom_user_agent = arguments.get("custom_user_agent")

    if "respect_robots_txt" in arguments:
        state.respect_robots_txt = arguments["respect_robots_txt"]

    if "rate_limit_delay" in arguments:
        delay = arguments["rate_limit_delay"]
        if delay < 0:
            return [_json_text({"error": "rate_limit_delay must be non-negative"})]
        state.rate_limit_delay = delay

    # Create manager to get profile info
    manager = AntiDetectionManager(
        profile=profile,
        custom_headers=state.custom_headers,
        custom_user_agent=state.custom_user_agent,
    )

    # Build response
    response = {
        "success": True,
        "status": "configured",
        "profile": profile.value,
        "profile_info": manager.get_profile_info(),
        "respect_robots_txt": state.respect_robots_txt,
        "rate_limit_delay": state.rate_limit_delay,
    }

    if profile == AntiDetectionProfile.CUSTOM:
        response["custom_headers"] = state.custom_headers
        if state.custom_user_agent:
            response["custom_user_agent"] = state.custom_user_agent

    logger.info("Anti-detection configured", profile=profile.value)
    return [_json_text(response)]


async def _handle_get_content(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle the get_content tool.

    Fetches a URL and extracts text content using BeautifulSoup.
    Supports recursive crawling with depth parameter.
    Uses the configured anti-detection settings.
    """
    from urllib.parse import urlparse

    url = arguments.get("url")
    if not url:
        return [_json_text({"success": False, "error": "url is required"})]

    depth = min(arguments.get("depth", 1), 3)  # Cap at 3
    max_pages_per_level = min(arguments.get("max_pages_per_level", 5), 20)
    selector = arguments.get("selector")
    include_links = arguments.get("include_links", True)
    include_images = arguments.get("include_images", False)
    include_meta = arguments.get("include_meta", True)

    # Get base domain for internal link filtering
    base_domain = urlparse(url).netloc

    # Track visited URLs to avoid duplicates
    visited: set[str] = set()

    async def fetch_single_page(page_url: str) -> Dict[str, Any] | None:
        """Fetch and extract content from a single page."""
        # Normalize URL
        normalized_url = page_url.rstrip("/")
        if normalized_url in visited:
            return None
        visited.add(normalized_url)

        # Check robots.txt if enabled
        state = get_scraping_state()
        if state.respect_robots_txt:
            from app.scraping.robots import get_robots_checker

            checker = get_robots_checker()
            allowed, reason = await checker.is_allowed(page_url)
            if not allowed:
                return {
                    "success": False,
                    "error": f"Access denied: {reason}",
                    "url": page_url,
                    "robots_blocked": True,
                }

        # Fetch the URL
        fetch_result = await fetch_url(page_url)
        if not fetch_result.success:
            return {
                "success": False,
                "error": f"Failed to fetch URL: {fetch_result.error}",
                "url": page_url,
                "status_code": fetch_result.status_code,
            }

        # Extract content
        from app.scraping.extractor import ContentExtractor

        extractor = ContentExtractor()

        if selector:
            content = extractor.extract_by_selector(
                fetch_result.content,
                selector,
                url=fetch_result.url,
            )
        else:
            content = extractor.extract(
                fetch_result.content,
                url=fetch_result.url,
                include_links=include_links,
                include_images=include_images,
                include_meta=include_meta,
            )

        if not content.success:
            return {
                "success": False,
                "error": content.error,
                "url": page_url,
            }

        # Build response
        page_data: Dict[str, Any] = {
            "success": True,
            "url": content.url,
            "title": content.title,
            "text": content.text,
            "language": content.language,
        }

        if content.headings:
            page_data["headings"] = content.headings

        if include_links and content.links:
            page_data["links"] = content.links

        if include_images and content.images:
            page_data["images"] = content.images

        if include_meta and content.meta:
            page_data["meta"] = content.meta

        return page_data

    def get_internal_links(page_data: Dict[str, Any]) -> list[str]:
        """Extract internal links from page data."""
        links = page_data.get("links", [])
        internal_links = []
        for link in links:
            link_url = link.get("url", "")
            is_external = link.get("external", True)
            if not is_external and link_url.startswith("http"):
                link_domain = urlparse(link_url).netloc
                if link_domain == base_domain:
                    normalized = link_url.rstrip("/")
                    if normalized not in visited:
                        internal_links.append(link_url)
        return internal_links

    # Single page (depth=1)
    if depth == 1:
        page_data = await fetch_single_page(url)
        if page_data is None:
            return [_json_text({"success": False, "error": "URL already visited"})]

        logger.info(
            "Content extracted",
            url=url,
            text_length=len(page_data.get("text", "")),
            links_count=len(page_data.get("links", [])),
        )
        return [_json_text(page_data)]

    # Multi-level crawl (depth > 1)
    results: Dict[str, Any] = {
        "success": True,
        "crawl_depth": depth,
        "max_pages_per_level": max_pages_per_level,
        "start_url": url,
        "pages": [],
        "summary": {
            "total_pages": 0,
            "total_text_length": 0,
            "pages_by_depth": {},
        },
    }

    # Depth 1: Start URL
    logger.info("Crawling depth 1", url=url)
    root_page = await fetch_single_page(url)
    if root_page is None or not root_page.get("success"):
        return [_json_text(root_page or {"success": False, "error": "Failed to fetch root URL"})]

    root_page["depth"] = 1
    results["pages"].append(root_page)
    results["summary"]["total_pages"] = 1
    results["summary"]["total_text_length"] = len(root_page.get("text", ""))
    results["summary"]["pages_by_depth"]["1"] = 1

    # Collect links for next level
    current_level_links = get_internal_links(root_page)[:max_pages_per_level]

    # Depth 2
    if depth >= 2 and current_level_links:
        logger.info("Crawling depth 2", num_links=len(current_level_links))
        next_level_links: list[str] = []
        depth_2_count = 0

        for link_url in current_level_links:
            page_data = await fetch_single_page(link_url)
            if page_data and page_data.get("success"):
                page_data["depth"] = 2
                results["pages"].append(page_data)
                results["summary"]["total_pages"] += 1
                results["summary"]["total_text_length"] += len(page_data.get("text", ""))
                depth_2_count += 1

                # Collect links for depth 3
                if depth >= 3:
                    next_level_links.extend(get_internal_links(page_data))

        results["summary"]["pages_by_depth"]["2"] = depth_2_count
        current_level_links = list(dict.fromkeys(next_level_links))[:max_pages_per_level]

    # Depth 3
    if depth >= 3 and current_level_links:
        logger.info("Crawling depth 3", num_links=len(current_level_links))
        depth_3_count = 0

        for link_url in current_level_links:
            page_data = await fetch_single_page(link_url)
            if page_data and page_data.get("success"):
                page_data["depth"] = 3
                results["pages"].append(page_data)
                results["summary"]["total_pages"] += 1
                results["summary"]["total_text_length"] += len(page_data.get("text", ""))
                depth_3_count += 1

        results["summary"]["pages_by_depth"]["3"] = depth_3_count

    logger.info(
        "Crawl completed",
        start_url=url,
        depth=depth,
        total_pages=results["summary"]["total_pages"],
        total_text_length=results["summary"]["total_text_length"],
    )

    return [_json_text(results)]


async def _handle_get_structure(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle the get_structure tool.

    Analyzes the structure of a web page, returning semantic sections,
    navigation, links, forms, and document outline.
    """
    url = arguments.get("url")
    if not url:
        return [_json_text({"success": False, "error": "url is required"})]

    # Check robots.txt if enabled
    state = get_scraping_state()
    if state.respect_robots_txt:
        from app.scraping.robots import get_robots_checker

        checker = get_robots_checker()
        allowed, reason = await checker.is_allowed(url)
        if not allowed:
            return [
                _json_text(
                    {
                        "success": False,
                        "error": f"Access denied: {reason}",
                        "url": url,
                        "robots_blocked": True,
                    }
                )
            ]

    include_navigation = arguments.get("include_navigation", True)
    include_internal_links = arguments.get("include_internal_links", True)
    include_external_links = arguments.get("include_external_links", True)
    include_forms = arguments.get("include_forms", True)
    include_outline = arguments.get("include_outline", True)

    # Fetch the URL
    fetch_result = await fetch_url(url)
    if not fetch_result.success:
        return [
            _json_text(
                {
                    "success": False,
                    "error": f"Failed to fetch URL: {fetch_result.error}",
                    "url": url,
                    "status_code": fetch_result.status_code,
                }
            )
        ]

    # Analyze structure
    from app.scraping.structure import StructureAnalyzer

    analyzer = StructureAnalyzer()
    structure = analyzer.analyze(fetch_result.content, url=fetch_result.url)

    if not structure.success:
        return [
            _json_text(
                {
                    "success": False,
                    "error": structure.error,
                    "url": url,
                }
            )
        ]

    # Build response
    response = {
        "success": True,
        "url": structure.url,
        "title": structure.title,
        "language": structure.language,
        "sections": structure.sections,
    }

    if include_navigation:
        response["navigation"] = structure.navigation

    if include_internal_links:
        response["internal_links"] = structure.internal_links

    if include_external_links:
        response["external_links"] = structure.external_links

    if include_forms:
        response["forms"] = structure.forms

    if include_outline:
        response["outline"] = structure.outline

    if structure.meta:
        response["meta"] = structure.meta

    logger.info(
        "Structure analyzed",
        url=url,
        sections_count=len(structure.sections),
        nav_links_count=len(structure.navigation),
        internal_links_count=len(structure.internal_links),
        external_links_count=len(structure.external_links),
    )
    return [_json_text(response)]


async def initialize_server() -> None:
    """Initialize server components."""
    logger.info("GOFR-DIG server initialized")


# Streamable HTTP setup
session_manager_http = StreamableHTTPSessionManager(
    app=app,
    event_store=None,
    json_response=False,
    stateless=False,
)


async def handle_streamable_http(scope, receive, send) -> None:
    """Handle HTTP requests."""
    await session_manager_http.handle_request(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(starlette_app) -> AsyncIterator[None]:
    """Manage server lifecycle."""
    logger.info("Starting GOFR-DIG server")
    await initialize_server()
    async with session_manager_http.run():
        yield


from starlette.applications import Starlette  # noqa: E402 - must import after MCP setup
from starlette.middleware.cors import CORSMiddleware  # noqa: E402
from starlette.routing import Mount  # noqa: E402

starlette_app = Starlette(
    debug=False,
    routes=[Mount("/mcp/", app=handle_streamable_http)],
    lifespan=lifespan,
)

starlette_app = CORSMiddleware(
    starlette_app,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    expose_headers=["Mcp-Session-Id"],
)


async def main(host: str = "0.0.0.0", port: int = 8030) -> None:
    """Run the server."""
    import uvicorn

    config = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
