#!/usr/bin/env python3
"""GOFR-DIG MCP Server - Hello World Implementation."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, AsyncIterator, Dict, List

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool

from gofr_common.mcp import json_text as _common_json_text, MCPResponseBuilder

from app.logger import session_logger as logger
from app.scraping import (
    AntiDetectionManager,
    AntiDetectionProfile,
    fetch_url,
)
from app.scraping.state import get_scraping_state
from app.exceptions import GofrDigError
from app.errors.mapper import error_to_mcp_response, RECOVERY_STRATEGIES

# Module-level configuration (set by main_mcp.py)
auth_service: Any = None
templates_dir_override: str | None = None
styles_dir_override: str | None = None
web_url_override: str | None = None
proxy_url_mode: bool = False

app = Server("gofr-dig-service")

# Initialize response builder with scraping-specific recovery strategies
_response_builder = MCPResponseBuilder()
_response_builder.set_recovery_strategies(RECOVERY_STRATEGIES)


def _json_text(data: Dict[str, Any]) -> TextContent:
    """Create JSON text content - uses gofr_common."""
    return _common_json_text(data)


def _error_response(
    error_code: str,
    message: str,
    details: Dict[str, Any] | None = None,
) -> List[TextContent]:
    """Create a standardized error response with recovery strategy.
    
    Args:
        error_code: Machine-readable error code (e.g., "INVALID_URL")
        message: Human-readable error message
        details: Optional additional context
        
    Returns:
        List with single TextContent containing JSON error response
    """
    response: Dict[str, Any] = {
        "success": False,
        "error_code": error_code,
        "error": message,
        "recovery_strategy": RECOVERY_STRATEGIES.get(
            error_code,
            "Review the error message and try again.",
        ),
    }
    if details:
        response["details"] = details
    
    logger.warning("Tool error", error_code=error_code, error_message=message, details=details)
    return [_json_text(response)]


def _exception_response(error: GofrDigError) -> List[TextContent]:
    """Convert GofrDigError to MCP response format.
    
    Args:
        error: The exception to convert
        
    Returns:
        List with single TextContent containing JSON error response
    """
    response = error_to_mcp_response(error)
    logger.warning("Tool exception", error_code=response["error_code"], error_message=response["message"])
    return [_json_text(response)]


def _estimate_tokens(text: str) -> int:
    """Estimate token count from text (approx 1 token per 4 characters)."""
    return len(text) // 4


def _truncate_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate text to fit within token limit.
    
    Args:
        text: Text to truncate
        max_tokens: Maximum tokens allowed
        
    Returns:
        Tuple of (truncated_text, was_truncated)
    """
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text, False
    
    # Truncate and try to end at a sentence or word boundary
    truncated = text[:max_chars]
    
    # Try to find a sentence ending
    last_period = truncated.rfind('. ')
    last_newline = truncated.rfind('\n')
    break_point = max(last_period, last_newline)
    
    if break_point > max_chars * 0.8:  # Only use if we keep at least 80%
        truncated = truncated[:break_point + 1]
    
    return truncated.rstrip() + "\n\n[Content truncated due to token limit]", True


def _apply_token_limit(page_data: Dict[str, Any], max_tokens: int) -> tuple[Dict[str, Any], bool]:
    """Apply token limit to a single page's content.
    
    Args:
        page_data: Page data dictionary with 'text' field
        max_tokens: Maximum tokens allowed
        
    Returns:
        Tuple of (modified_page_data, was_truncated)
    """
    if not page_data.get("success", False):
        return page_data, False
    
    text = page_data.get("text", "")
    if not text:
        return page_data, False
    
    truncated_text, was_truncated = _truncate_to_tokens(text, max_tokens)
    if was_truncated:
        page_data = page_data.copy()
        page_data["text"] = truncated_text
        page_data["truncated"] = True
        page_data["original_tokens"] = _estimate_tokens(text)
        page_data["returned_tokens"] = _estimate_tokens(truncated_text)
    
    return page_data, was_truncated


def _apply_token_limit_multipage(results: Dict[str, Any], max_tokens: int) -> tuple[Dict[str, Any], bool]:
    """Apply token limit across multi-page crawl results.
    
    Truncates pages in reverse order (deepest first) to preserve most important content.
    
    Args:
        results: Multi-page results with 'pages' array and root 'text'
        max_tokens: Maximum tokens allowed
        
    Returns:
        Tuple of (modified_results, was_truncated)
    """
    # Calculate total tokens across all content
    root_text = results.get("text", "") or ""
    root_tokens = _estimate_tokens(root_text)
    
    pages = results.get("pages", [])
    page_tokens = [_estimate_tokens(p.get("text", "") or "") for p in pages]
    total_tokens = root_tokens + sum(page_tokens)
    
    if total_tokens <= max_tokens:
        return results, False
    
    # Need to truncate - work backwards from deepest pages
    results = results.copy()
    results["pages"] = [p.copy() for p in pages]
    results["truncated"] = True
    results["original_tokens"] = total_tokens
    
    tokens_to_remove = total_tokens - max_tokens
    pages_removed = 0
    pages_truncated = 0
    
    # First, try removing pages from the end (deepest first)
    while tokens_to_remove > 0 and results["pages"]:
        last_page = results["pages"][-1]
        last_page_tokens = _estimate_tokens(last_page.get("text", "") or "")
        
        if last_page_tokens <= tokens_to_remove:
            # Remove entire page
            results["pages"].pop()
            tokens_to_remove -= last_page_tokens
            pages_removed += 1
        else:
            # Truncate this page's text
            remaining_tokens_for_page = last_page_tokens - tokens_to_remove
            if remaining_tokens_for_page < 500:  # Too small, remove it
                results["pages"].pop()
                tokens_to_remove -= last_page_tokens
                pages_removed += 1
            else:
                truncated_text, _ = _truncate_to_tokens(
                    last_page.get("text", ""),
                    remaining_tokens_for_page
                )
                results["pages"][-1]["text"] = truncated_text
                results["pages"][-1]["truncated"] = True
                pages_truncated += 1
                tokens_to_remove = 0
    
    # If still over, truncate root text
    if tokens_to_remove > 0 and root_text:
        remaining_tokens_for_root = root_tokens - tokens_to_remove
        if remaining_tokens_for_root > 500:
            truncated_text, _ = _truncate_to_tokens(root_text, remaining_tokens_for_root)
            results["text"] = truncated_text
    
    # Update summary
    results["returned_tokens"] = max_tokens
    results["pages_removed_for_limit"] = pages_removed
    results["pages_truncated_for_limit"] = pages_truncated
    
    # Recalculate summary
    actual_pages = len(results["pages"])
    actual_text_length = len(results.get("text", "") or "")
    for page in results["pages"]:
        actual_text_length += len(page.get("text", "") or "")
    
    results["summary"]["total_pages"] = actual_pages
    results["summary"]["total_text_length"] = actual_text_length
    
    return results, True


@app.list_tools()
async def handle_list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="ping",
            description="Health check - returns server status. Use to verify the MCP server is running. Returns: {status: 'ok', service: 'gofr-dig'}",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="hello_world",
            description="Returns a greeting message. A simple test tool. Returns: {message: 'Hello, <name>!'}",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name to greet. Defaults to 'World' if not provided.",
                    }
                },
            },
        ),
        Tool(
            name="set_antidetection",
            description="""Configure anti-detection settings for web scraping. Call this BEFORE get_content or get_structure to customize scraping behavior. Settings persist for the session.

PROFILES:
- stealth: Maximum protection with browser-like headers. Use for sites with strict bot detection.
- balanced: Good protection for most sites (default). Recommended starting point.
- none: Minimal headers, fastest but easily detected. Use for APIs or permissive sites.
- custom: Define your own headers and user agent.
- browser_tls: Uses curl_cffi to impersonate Chrome's TLS fingerprint. Use for sites like Wikipedia that use TLS fingerprinting to detect Python HTTP libraries.

TOKEN LIMIT: max_tokens controls how much content is returned (default: 100000). Content exceeding this will be truncated, with deepest pages removed first.

Returns: {success: true, profile: '...', respect_robots_txt: bool, rate_limit_delay: number, max_tokens: number}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "string",
                        "enum": ["stealth", "balanced", "none", "custom", "browser_tls"],
                        "description": "Anti-detection profile. Use 'balanced' for most sites, 'stealth' for sites with bot detection, 'browser_tls' for sites using TLS fingerprinting (e.g., Wikipedia).",
                    },
                    "custom_headers": {
                        "type": "object",
                        "description": "Custom headers when profile='custom'. Example: {\"Accept-Language\": \"en-US\"}",
                        "additionalProperties": {"type": "string"},
                    },
                    "custom_user_agent": {
                        "type": "string",
                        "description": "Custom User-Agent when profile='custom'. Example: 'Mozilla/5.0 (compatible; MyBot/1.0)'",
                    },
                    "respect_robots_txt": {
                        "type": "boolean",
                        "description": "Follow robots.txt rules (default: true). Set false to access disallowed paths (use responsibly).",
                    },
                    "rate_limit_delay": {
                        "type": "number",
                        "description": "Seconds to wait between requests (default: 1.0). Increase for rate-limited sites.",
                        "minimum": 0,
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "Maximum tokens to return in responses (default: 100000). Content will be truncated if exceeded. 1 token ≈ 4 characters.",
                        "minimum": 1000,
                        "maximum": 1000000,
                        "default": 100000,
                    },
                },
                "required": ["profile"],
            },
        ),
        Tool(
            name="get_content",
            description="""Fetch a web page and extract its text content. Supports recursive crawling with depth parameter.

USE CASES:
- depth=1: Extract content from a single page (default)
- depth=2: Extract from page AND pages it links to (great for documentation sites)
- depth=3: Three levels deep (use sparingly, can be slow)

RETURNS for depth=1: {success, url, title, text, language, links?, headings?, images?, meta?}
RETURNS for depth>1: Same fields at root (from first page) PLUS {pages: [...], summary: {total_pages, total_text_length, pages_by_depth}}

TIPS:
- Use selector='#content' to focus on main content area
- Set include_links=false if you only need text
- Respects robots.txt and rate limits from set_antidetection""",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to fetch (must include http:// or https://)",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Crawl depth: 1=single page, 2=follow links once, 3=follow twice. Use 1 for single pages, 2-3 for documentation.",
                        "minimum": 1,
                        "maximum": 3,
                        "default": 1,
                    },
                    "max_pages_per_level": {
                        "type": "integer",
                        "description": "Max pages per depth level (default: 5, max: 20). Lower values = faster crawls.",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 5,
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector to extract specific elements. Examples: '#content', 'article', '.main-text'",
                    },
                    "include_links": {
                        "type": "boolean",
                        "description": "Include extracted links (default: true). Set false for text-only extraction.",
                    },
                    "include_images": {
                        "type": "boolean",
                        "description": "Include image URLs and alt text (default: false). Enable for image-heavy pages.",
                    },
                    "include_meta": {
                        "type": "boolean",
                        "description": "Include page metadata like description, keywords, og:tags (default: true).",
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="get_structure",
            description="""Analyze the structure of a web page WITHOUT extracting all text content. Use this to understand page layout before deciding what to extract with get_content.

RETURNS: {success, url, title, language, sections: [...], navigation?: [...], internal_links?: [...], external_links?: [...], forms?: [...], outline?: [...]}

USE get_structure WHEN:
- You need to find the right CSS selector for get_content
- You want to understand page organization before crawling
- You need to find forms, navigation, or specific sections

USE get_content WHEN:
- You need the actual text content
- You want to extract and process page text""",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to analyze (must include http:// or https://)",
                    },
                    "include_navigation": {
                        "type": "boolean",
                        "description": "Include navigation menus and their links (default: true)",
                    },
                    "include_internal_links": {
                        "type": "boolean",
                        "description": "Include links to same domain (default: true)",
                    },
                    "include_external_links": {
                        "type": "boolean",
                        "description": "Include links to other domains (default: true)",
                    },
                    "include_forms": {
                        "type": "boolean",
                        "description": "Include form fields and actions (default: true)",
                    },
                    "include_outline": {
                        "type": "boolean",
                        "description": "Include heading hierarchy h1-h6 (default: true)",
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

    return _error_response("UNKNOWN_TOOL", f"Unknown tool: {name}", {"tool_name": name})


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
        return _error_response(
            "INVALID_PROFILE",
            f"Invalid profile: {profile_str}",
            {"valid_profiles": valid_profiles},
        )

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
            return _error_response(
                "INVALID_RATE_LIMIT",
                "rate_limit_delay must be non-negative",
                {"provided_value": delay},
            )
        state.rate_limit_delay = delay

    if "max_tokens" in arguments:
        max_tokens = arguments["max_tokens"]
        if max_tokens < 1000:
            return _error_response(
                "INVALID_MAX_TOKENS",
                "max_tokens must be at least 1000",
                {"provided_value": max_tokens},
            )
        if max_tokens > 1000000:
            return _error_response(
                "INVALID_MAX_TOKENS",
                "max_tokens cannot exceed 1000000",
                {"provided_value": max_tokens},
            )
        state.max_tokens = max_tokens

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
        "max_tokens": state.max_tokens,
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
        return _error_response("INVALID_URL", "url is required")

    # Validate and clamp depth (1-3) and max_pages_per_level (1-20)
    depth = max(1, min(arguments.get("depth", 1), 3))
    max_pages_per_level = max(1, min(arguments.get("max_pages_per_level", 5), 20))
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

        # Apply token limit truncation
        state = get_scraping_state()
        page_data, truncated = _apply_token_limit(page_data, state.max_tokens)

        logger.info(
            "Content extracted",
            url=url,
            text_length=len(page_data.get("text", "")),
            links_count=len(page_data.get("links", [])),
            truncated=truncated,
        )
        return [_json_text(page_data)]

    # Multi-level crawl (depth > 1)
    results: Dict[str, Any] = {
        "success": True,
        "crawl_depth": depth,
        "max_pages_per_level": max_pages_per_level,
        "start_url": url,
        # Top-level content fields will be populated from root page
        "url": None,
        "title": None,
        "text": None,
        "language": None,
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

    # Populate top-level fields from root page
    results["url"] = root_page.get("url")
    results["title"] = root_page.get("title")
    results["text"] = root_page.get("text")
    results["language"] = root_page.get("language")
    if root_page.get("headings"):
        results["headings"] = root_page.get("headings")
    if root_page.get("links"):
        results["links"] = root_page.get("links")
    if root_page.get("images"):
        results["images"] = root_page.get("images")
    if root_page.get("meta"):
        results["meta"] = root_page.get("meta")

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

    # Apply token limit truncation to multi-page results
    state = get_scraping_state()
    results, truncated = _apply_token_limit_multipage(results, state.max_tokens)

    logger.info(
        "Crawl completed",
        start_url=url,
        depth=depth,
        total_pages=results["summary"]["total_pages"],
        total_text_length=results["summary"]["total_text_length"],
        truncated=truncated,
    )

    return [_json_text(results)]


async def _handle_get_structure(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle the get_structure tool.

    Analyzes the structure of a web page, returning semantic sections,
    navigation, links, forms, and document outline.
    """
    url = arguments.get("url")
    if not url:
        return _error_response("INVALID_URL", "url is required")

    # Check robots.txt if enabled
    state = get_scraping_state()
    if state.respect_robots_txt:
        from app.scraping.robots import get_robots_checker

        checker = get_robots_checker()
        allowed, reason = await checker.is_allowed(url)
        if not allowed:
            return _error_response(
                "ROBOTS_BLOCKED",
                f"Access denied: {reason}",
                {"url": url},
            )

    include_navigation = arguments.get("include_navigation", True)
    include_internal_links = arguments.get("include_internal_links", True)
    include_external_links = arguments.get("include_external_links", True)
    include_forms = arguments.get("include_forms", True)
    include_outline = arguments.get("include_outline", True)

    # Fetch the URL
    fetch_result = await fetch_url(url)
    if not fetch_result.success:
        return _error_response(
            "FETCH_ERROR",
            f"Failed to fetch URL: {fetch_result.error}",
            {"url": url, "status_code": fetch_result.status_code},
        )

    # Analyze structure
    from app.scraping.structure import StructureAnalyzer

    analyzer = StructureAnalyzer()
    structure = analyzer.analyze(fetch_result.content, url=fetch_result.url)

    if not structure.success:
        return _error_response(
            "EXTRACTION_ERROR",
            structure.error or "Failed to analyze page structure",
            {"url": url},
        )

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


from gofr_common.web import create_mcp_starlette_app  # noqa: E402 - must import after MCP setup

starlette_app = create_mcp_starlette_app(
    mcp_handler=handle_streamable_http,
    lifespan=lifespan,
    env_prefix="GOFR_DIG",
)


async def main(host: str = "0.0.0.0", port: int = 8030) -> None:
    """Run the server."""
    import uvicorn

    config = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
