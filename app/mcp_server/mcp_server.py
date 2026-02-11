#!/usr/bin/env python3
"""GOFR-DIG MCP Server."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, AsyncIterator, Dict, List

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool, ToolAnnotations

from gofr_common.mcp import json_text as _common_json_text, MCPResponseBuilder

from app.logger import session_logger as logger
from app.scraping import (
    AntiDetectionManager,
    AntiDetectionProfile,
    FetchResult,
    fetch_url,
)
from app.scraping.state import get_scraping_state
from app.exceptions import GofrDigError
from app.errors.mapper import error_to_mcp_response, RECOVERY_STRATEGIES
from app.session.manager import SessionManager
from app.config import Config

try:
    from gofr_common.auth.exceptions import AuthError
except ImportError:
    AuthError = None  # type: ignore[assignment,misc]

try:
    from gofr_common.storage.exceptions import PermissionDeniedError
except ImportError:
    PermissionDeniedError = None  # type: ignore[assignment,misc]

# Shared auth_tokens schema fragment — added to every tool except ping.
AUTH_TOKENS_SCHEMA = {
    "auth_tokens": {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "One or more JWT tokens for authentication. "
            "The server verifies each token and uses the first group "
            "from the first valid token to scope session access. "
            "Omit for anonymous/public access."
        ),
    },
}

# Module-level configuration (set by main_mcp.py)
auth_service: Any = None


def _resolve_group_from_tokens(auth_tokens: list[str] | None) -> str | None:
    """Resolve the primary group from auth_tokens passed as a tool parameter.

    Returns the first group from the first valid token, or None if
    auth is disabled or no tokens provided.

    Raises AuthError if tokens are provided but all are invalid.
    """
    if auth_service is None:
        return None  # auth disabled (--no-auth)

    if not auth_tokens:
        return None  # anonymous → public

    last_error: Exception | None = None
    for raw_token in auth_tokens:
        # Strip "Bearer " prefix if present
        if raw_token.lower().startswith("bearer "):
            raw_token = raw_token[7:].strip()
        else:
            raw_token = raw_token.strip()

        if not raw_token:
            continue

        try:
            token_info = auth_service.verify_token(raw_token)
            if token_info.groups:
                return token_info.groups[0]  # primary group = first in list
            return None  # valid token, no groups → anonymous
        except Exception as e:
            if AuthError is not None and isinstance(e, AuthError):
                last_error = e
                continue  # try next token
            raise  # unexpected error, propagate

    # All tokens failed
    if last_error:
        raise last_error
    return None
templates_dir_override: str | None = None
styles_dir_override: str | None = None
web_url_override: str | None = None
proxy_url_mode: bool = False
session_manager: SessionManager | None = None

app = Server(
    "gofr-dig-service",
    instructions="""You are connected to gofr-dig, a web scraping and page-analysis service.

RECOMMENDED WORKFLOW:
1. (Optional) set_antidetection — configure a scraping profile before fetching. Use 'balanced' for most sites, 'browser_tls' for sites like Wikipedia. Skip this step for simple fetches (sensible defaults apply).
2. get_structure — analyze a page's layout to discover CSS selectors, navigation, forms, and heading outline. Use this to decide WHAT to extract.
3. get_content — fetch and extract text. For a single page use depth=1 (default). For documentation sites use depth=2 or 3 (these automatically store results in a session because the payload is large).
4. If a session_id is returned (depth > 1, or session=true), retrieve content with get_session_chunk(session_id, chunk_index) iterating chunk_index from 0 to total_chunks-1. Use get_session_info to check session metadata.
5. list_sessions — browse all stored sessions from previous scrapes.
6. get_session_urls — get plain HTTP URLs for every chunk (useful for automation fan-out to N8N, Make, Zapier).

ALL ERRORS follow a standard shape: {success: false, error_code, message, details, recovery_strategy}. The recovery_strategy field tells you how to fix the problem.
""",
)

# Initialize response builder with scraping-specific recovery strategies
_response_builder = MCPResponseBuilder()
_response_builder.set_recovery_strategies(RECOVERY_STRATEGIES)


def get_session_manager() -> SessionManager:
    """Get or initialize the session manager."""
    global session_manager
    if session_manager is None:
        storage_dir = Config.get_storage_dir() / "sessions"
        session_manager = SessionManager(storage_dir)
    return session_manager


def _json_text(data: Any) -> TextContent:
    """Create JSON text content - uses gofr_common."""
    return _common_json_text(data)


def _classify_fetch_error(result: FetchResult) -> str:
    """Map a failed FetchResult to a specific error code.

    Classifies HTTP status codes and error strings into granular error codes
    so callers receive actionable recovery strategies instead of generic
    FETCH_ERROR for every failure.
    """
    if result.status_code == 404:
        return "URL_NOT_FOUND"
    if result.status_code == 403:
        return "ACCESS_DENIED"
    if result.status_code == 429 or result.rate_limited:
        return "RATE_LIMITED"
    if result.status_code >= 500:
        return "FETCH_ERROR"
    error_str = (result.error or "").lower()
    if "timeout" in error_str or "timed out" in error_str:
        return "TIMEOUT_ERROR"
    if "connect" in error_str or "resolve" in error_str or "dns" in error_str:
        return "CONNECTION_ERROR"
    return "FETCH_ERROR"


def _classify_extraction_error(error_msg: str) -> str:
    """Map a content extraction error to a specific error code.

    Classifies extractor error strings into granular codes so callers
    receive targeted recovery strategies.
    """
    msg = error_msg.lower()
    if "did not match" in msg and "selector" in msg:
        return "SELECTOR_NOT_FOUND"
    if "invalid selector" in msg:
        return "INVALID_SELECTOR"
    if "encoding" in msg or "decode" in msg:
        return "ENCODING_ERROR"
    return "EXTRACTION_ERROR"


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
            description=(
                "Health check. Returns {status: 'ok', service: 'gofr-dig'} when the server is reachable. "
                "Call this first to verify connectivity before making scraping requests."
            ),
            inputSchema={"type": "object", "properties": {}},
            annotations=ToolAnnotations(
                title="Ping",
                readOnlyHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="set_antidetection",
            description=(
                "Configure anti-detection settings BEFORE calling get_content or get_structure. "
                "Settings persist for the remainder of this MCP session.\n\n"
                "PROFILES (choose one):\n"
                "- 'balanced' \u2014 standard browser headers, fixed User-Agent. Good default for most sites.\n"
                "- 'stealth'  \u2014 full browser headers with rotating User-Agent. Use when a site blocks you.\n"
                "- 'browser_tls' \u2014 impersonates Chrome TLS fingerprint via curl_cffi. Required for sites that use TLS fingerprinting (e.g. Wikipedia).\n"
                "- 'none'     \u2014 minimal headers. Use only for APIs or sites you control.\n"
                "- 'custom'   \u2014 supply your own custom_headers and custom_user_agent.\n\n"
                "OTHER SETTINGS:\n"
                "- respect_robots_txt (default true) \u2014 honour robots.txt rules.\n"
                "- rate_limit_delay (default 1.0s, range 0\u201360) \u2014 pause between requests.\n"
                "- max_tokens (default 100000, range 1000\u20131000000) \u2014 cap response size; \u22484 chars/token. "
                "Content exceeding this is truncated (deepest pages removed first).\n\n"
                "Returns: {success, profile, respect_robots_txt, rate_limit_delay, max_tokens}.\n"
                "Errors: INVALID_PROFILE, INVALID_RATE_LIMIT, INVALID_MAX_TOKENS."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "string",
                        "enum": ["stealth", "balanced", "none", "custom", "browser_tls"],
                        "description": (
                            "Anti-detection profile to activate. "
                            "Start with 'balanced'; escalate to 'stealth' or 'browser_tls' if you get FETCH_ERROR or empty content."
                        ),
                    },
                    "custom_headers": {
                        "type": "object",
                        "description": "Custom HTTP headers (only used with profile='custom'). Example: {\"Accept-Language\": \"en-US\"}",
                        "additionalProperties": {"type": "string"},
                    },
                    "custom_user_agent": {
                        "type": "string",
                        "description": "Custom User-Agent string (only used with profile='custom').",
                    },
                    "respect_robots_txt": {
                        "type": "boolean",
                        "description": "Honour robots.txt rules (default: true). Set false only when you have explicit permission.",
                    },
                    "rate_limit_delay": {
                        "type": "number",
                        "description": "Seconds between requests (default: 1.0, range 0\u201360). Increase if you see rate-limit errors.",
                        "minimum": 0,
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "Max tokens in responses (default: 100000). 1 token \u2248 4 characters. Reduce for faster responses; increase to capture full large pages.",
                        "minimum": 1000,
                        "maximum": 1000000,
                        "default": 100000,
                    },
                    **AUTH_TOKENS_SCHEMA,
                },
                "required": ["profile"],
            },
            annotations=ToolAnnotations(
                title="Set Anti-Detection",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="get_content",
            description=(
                "Fetch a web page and extract its readable text. "
                "This is the primary scraping tool.\n\n"
                "DEPTH BEHAVIOUR:\n"
                "- depth=1 (default): scrape a single page. Returns inline JSON: "
                "{success, url, title, text, language, links, headings, images, meta}.\n"
                "- depth=2: scrape the page AND the pages it links to. "
                "Automatically stores results in a server-side session (payload is too large for inline). "
                "Returns: {success, session_id, url, total_chunks, total_size, crawl_depth, total_pages}.\n"
                "- depth=3: three levels deep (slow, use sparingly). Same session response.\n\n"
                "SESSION MODE:\n"
                "When the response contains a session_id (depth>1, or session=true with depth=1), "
                "use get_session_chunk(session_id, chunk_index) to retrieve text, "
                "iterating chunk_index from 0 to total_chunks-1.\n\n"
                "TIPS:\n"
                "- Call get_structure first to find a good CSS selector, then pass it as 'selector'.\n"
                "- Use include_links=false and include_meta=false if you only need text.\n"
                "- If you get ROBOTS_BLOCKED, call set_antidetection with respect_robots_txt=false.\n"
                "- If you get FETCH_ERROR, try set_antidetection with profile='stealth' or 'browser_tls'.\n\n"
                "Errors: INVALID_URL, FETCH_ERROR, ROBOTS_BLOCKED, EXTRACTION_ERROR, "
                "MAX_DEPTH_EXCEEDED, MAX_PAGES_EXCEEDED."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to fetch (must start with http:// or https://).",
                    },
                    "depth": {
                        "type": "integer",
                        "description": (
                            "Crawl depth. 1 = single page (inline response). "
                            "2 = page + its links (auto-session). 3 = two levels of links (auto-session). "
                            "Default 1."
                        ),
                        "minimum": 1,
                        "maximum": 3,
                        "default": 1,
                    },
                    "max_pages_per_level": {
                        "type": "integer",
                        "description": "Max pages fetched per depth level (default 5, max 20). Keep low to avoid slow crawls.",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 5,
                    },
                    "selector": {
                        "type": "string",
                        "description": (
                            "CSS selector to extract only matching elements. "
                            "Examples: '#main-content', 'article', '.post-body'. "
                            "Omit to extract the full page."
                        ),
                    },
                    "include_links": {
                        "type": "boolean",
                        "description": "Include extracted hyperlinks in the result (default true). Set false for text-only.",
                    },
                    "include_images": {
                        "type": "boolean",
                        "description": "Include image URLs and alt text (default false).",
                    },
                    "include_meta": {
                        "type": "boolean",
                        "description": "Include page metadata: description, keywords, Open Graph tags (default true).",
                    },
                    "session": {
                        "type": "boolean",
                        "description": (
                            "Force session storage and return a session_id instead of inline content. "
                            "Automatically enabled when depth > 1. Useful for large single pages too."
                        ),
                    },
                    "filter_noise": {
                        "type": "boolean",
                        "description": (
                            "Strip advertisement / cookie-banner noise from the extracted text. "
                            "Removes ad-related HTML elements (by class/id) and filters noise "
                            "lines such as 'Advertisement', 'Sponsored Content', and cookie "
                            "consent prompts. Default true."
                        ),
                        "default": True,
                    },
                    "chunk_size": {
                        "type": "integer",
                        "description": "Session chunk size in characters (default 4000). Only used when session storage is active.",
                    },
                    **AUTH_TOKENS_SCHEMA,
                },
                "required": ["url"],
            },
            annotations=ToolAnnotations(
                title="Get Content",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            ),
        ),
        Tool(
            name="get_structure",
            description=(
                "Analyze a web page's structure WITHOUT extracting full text. "
                "Use this BEFORE get_content to discover the page layout and find CSS selectors.\n\n"
                "Returns: {success, url, title, language, sections, navigation, "
                "internal_links, external_links, forms, outline}.\n\n"
                "WHEN TO USE:\n"
                "- You want to find the right CSS selector to pass to get_content(selector=...).\n"
                "- You need to see the heading hierarchy or navigation structure.\n"
                "- You want to discover forms or distinguish internal vs. external links.\n\n"
                "WHEN TO USE get_content INSTEAD:\n"
                "- You need the actual text content of a page.\n\n"
                "Errors: INVALID_URL, FETCH_ERROR, ROBOTS_BLOCKED, EXTRACTION_ERROR."
            ),
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
                        "description": "Include HTML forms with their fields and actions (default true).",
                    },
                    "include_outline": {
                        "type": "boolean",
                        "description": "Include heading hierarchy (h1\u2013h6) as an outline (default true).",
                    },
                    **AUTH_TOKENS_SCHEMA,
                },
                "required": ["url"],
            },
            annotations=ToolAnnotations(
                title="Get Structure",
                readOnlyHint=True,
                openWorldHint=True,
            ),
        ),
        Tool(
            name="get_session_info",
            description=(
                "Get metadata for a stored scraping session. "
                "Returns: {success, session_id, url, total_chunks, total_size, created_at}.\n\n"
                "Use this to find out how many chunks a session has before iterating with get_session_chunk. "
                "The session_id comes from a previous get_content call (depth>1, or session=true)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session GUID returned by get_content when session storage was used.",
                    },
                    **AUTH_TOKENS_SCHEMA,
                },
                "required": ["session_id"],
            },
            annotations=ToolAnnotations(
                title="Get Session Info",
                readOnlyHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="get_session_chunk",
            description=(
                "Retrieve one chunk of text from a stored session. "
                "Returns: {success, session_id, chunk_index, total_chunks, content}.\n\n"
                "To read all content: iterate chunk_index from 0 to total_chunks-1. "
                "Get total_chunks from get_session_info or from the get_content response that created the session."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session GUID from a previous get_content call.",
                    },
                    "chunk_index": {
                        "type": "integer",
                        "description": "Zero-based chunk index (0 to total_chunks-1).",
                    },
                    **AUTH_TOKENS_SCHEMA,
                },
                "required": ["session_id", "chunk_index"],
            },
            annotations=ToolAnnotations(
                title="Get Session Chunk",
                readOnlyHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="list_sessions",
            description=(
                "List all stored scraping sessions. "
                "Returns: {success, sessions: [{session_id, url, total_chunks, total_size, created_at}], total}.\n\n"
                "Use this to discover sessions from earlier scrapes. "
                "Then call get_session_info or get_session_chunk with any session_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    **AUTH_TOKENS_SCHEMA,
                },
            },
            annotations=ToolAnnotations(
                title="List Sessions",
                readOnlyHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="get_session_urls",
            description=(
                "Get a list of plain HTTP URLs for every chunk in a session. "
                "Returns: {success, session_id, url, total_chunks, chunk_urls: [url, ...]}.\n\n"
                "Each URL is a ready-to-GET REST endpoint that returns one chunk's text. "
                "Designed for automation services (N8N, Make, Zapier) that can fan-out HTTP requests.\n\n"
                "Typical flow: get_content(depth=2) \u2192 get_session_urls(session_id) \u2192 HTTP GET each chunk_url."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session GUID from a previous get_content call.",
                    },
                    "base_url": {
                        "type": "string",
                        "description": (
                            "Override the web-server base URL (e.g. 'http://myhost:PORT'). "
                            "Auto-detected from GOFR_DIG_WEB_URL env or defaults to localhost if omitted."
                        ),
                    },
                    **AUTH_TOKENS_SCHEMA,
                },
                "required": ["session_id"],
            },
            annotations=ToolAnnotations(
                title="Get Session URLs",
                readOnlyHint=True,
                openWorldHint=False,
            ),
        ),
    ]


@app.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool invocations."""
    logger.info("Tool called", tool=name, args=arguments)

    if name == "ping":
        return [_json_text({"status": "ok", "service": "gofr-dig"})]

    if name == "set_antidetection":
        return await _handle_set_antidetection(arguments)

    if name == "get_content":
        return await _handle_get_content(arguments)

    if name == "get_structure":
        return await _handle_get_structure(arguments)

    if name == "get_session_info":
        return await _handle_get_session_info(arguments)

    if name == "get_session_chunk":
        return await _handle_get_session_chunk(arguments)

    if name == "list_sessions":
        return await _handle_list_sessions(arguments)

    if name == "get_session_urls":
        return await _handle_get_session_urls(arguments)

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
    filter_noise = arguments.get("filter_noise", True)
    use_session = arguments.get("session", False)
    chunk_size = arguments.get("chunk_size")

    # Auto-force session mode for multi-page crawls (depth > 1 produces large payloads)
    if depth > 1:
        use_session = True

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
            error_code = _classify_fetch_error(fetch_result)
            return {
                "success": False,
                "error_code": error_code,
                "error": f"Failed to fetch URL: {fetch_result.error}",
                "url": page_url,
                "status_code": fetch_result.status_code,
                "recovery_strategy": RECOVERY_STRATEGIES.get(
                    error_code, "Check the URL and try again."
                ),
            }

        # Extract content
        from app.scraping.extractor import ContentExtractor

        extractor = ContentExtractor()

        if selector:
            content = extractor.extract_by_selector(
                fetch_result.content,
                selector,
                url=fetch_result.url,
                filter_noise=filter_noise,
            )
        else:
            content = extractor.extract(
                fetch_result.content,
                url=fetch_result.url,
                include_links=include_links,
                include_images=include_images,
                include_meta=include_meta,
                filter_noise=filter_noise,
            )

        if not content.success:
            error_code = _classify_extraction_error(content.error or "")
            return {
                "success": False,
                "error_code": error_code,
                "error": content.error,
                "url": page_url,
                "recovery_strategy": RECOVERY_STRATEGIES.get(
                    error_code,
                    "Try a different selector or check the page structure.",
                ),
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

        # Handle session storage if requested
        if use_session:
            manager = get_session_manager()
            # Use provided chunk_size or default to 4000
            c_size = chunk_size if chunk_size is not None else 4000

            # Resolve group from auth_tokens
            auth_tokens = arguments.get("auth_tokens")
            try:
                group = _resolve_group_from_tokens(auth_tokens)
            except Exception as e:
                if AuthError is not None and isinstance(e, AuthError):
                    return _error_response("AUTH_ERROR", str(e))
                raise

            try:
                session_id = manager.create_session(
                    url=url, content=page_data, chunk_size=c_size, group=group,
                )

                # Get session info for response
                info = manager.get_session_info(session_id)

                return [
                    _json_text(
                        {
                            "success": True,
                            "session_id": session_id,
                            "url": url,
                            "total_chunks": info["total_chunks"],
                            "total_size": info["total_size_bytes"],
                            "chunk_size": info["chunk_size"],
                            "created_at": info["created_at"],
                        }
                    )
                ]
            except GofrDigError as e:
                return _exception_response(e)
            except Exception as e:
                logger.error("Failed to create session", error=str(e), url=url)
                return _error_response("SESSION_ERROR", f"Failed to create session: {e}", {"url": url})

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

    # Handle session storage if requested (same as depth=1)
    if use_session:
        manager = get_session_manager()
        c_size = chunk_size if chunk_size is not None else 4000

        # Resolve group from auth_tokens
        auth_tokens = arguments.get("auth_tokens")
        try:
            group = _resolve_group_from_tokens(auth_tokens)
        except Exception as e:
            if AuthError is not None and isinstance(e, AuthError):
                return _error_response("AUTH_ERROR", str(e))
            raise

        try:
            session_id = manager.create_session(
                url=url, content=results, chunk_size=c_size, group=group,
            )
            info = manager.get_session_info(session_id)

            return [
                _json_text(
                    {
                        "success": True,
                        "session_id": session_id,
                        "url": url,
                        "total_chunks": info["total_chunks"],
                        "total_size": info["total_size_bytes"],
                        "chunk_size": info["chunk_size"],
                        "created_at": info["created_at"],
                        "crawl_depth": depth,
                        "total_pages": results["summary"]["total_pages"],
                    }
                )
            ]
        except GofrDigError as e:
            return _exception_response(e)
        except Exception as e:
            logger.error("Failed to create session", error=str(e), url=url)
            return _error_response(
                "SESSION_ERROR", f"Failed to create session: {e}", {"url": url}
            )

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
        error_code = _classify_fetch_error(fetch_result)
        return _error_response(
            error_code,
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


async def _handle_get_session_info(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_session_info tool call."""
    session_id = arguments.get("session_id")
    if not session_id:
        return _error_response("INVALID_ARGUMENT", "session_id is required")

    auth_tokens = arguments.get("auth_tokens")
    try:
        group = _resolve_group_from_tokens(auth_tokens)
    except Exception as e:
        if AuthError is not None and isinstance(e, AuthError):
            return _error_response("AUTH_ERROR", str(e))
        raise

    try:
        manager = get_session_manager()
        info = manager.get_session_info(session_id, group=group)
        return [_json_text(info)]
    except Exception as e:
        if PermissionDeniedError is not None and isinstance(e, PermissionDeniedError):
            return _error_response("PERMISSION_DENIED", str(e), {"session_id": session_id})
        if isinstance(e, GofrDigError):
            return _exception_response(e)
        logger.error("Unexpected error in get_session_info", error=str(e), session_id=session_id)
        return _error_response("SESSION_ERROR", f"Unexpected error: {e}", {"session_id": session_id})


async def _handle_get_session_chunk(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_session_chunk tool call."""
    session_id = arguments.get("session_id")
    chunk_index = arguments.get("chunk_index")

    if not session_id:
        return _error_response("INVALID_ARGUMENT", "session_id is required")
    if chunk_index is None:
        return _error_response("INVALID_ARGUMENT", "chunk_index is required")

    auth_tokens = arguments.get("auth_tokens")
    try:
        group = _resolve_group_from_tokens(auth_tokens)
    except Exception as e:
        if AuthError is not None and isinstance(e, AuthError):
            return _error_response("AUTH_ERROR", str(e))
        raise

    try:
        manager = get_session_manager()
        chunk_data = manager.get_chunk(session_id, chunk_index, group=group)
        return [_json_text(chunk_data)]
    except Exception as e:
        if PermissionDeniedError is not None and isinstance(e, PermissionDeniedError):
            return _error_response("PERMISSION_DENIED", str(e), {"session_id": session_id})
        if isinstance(e, GofrDigError):
            return _exception_response(e)
        logger.error("Unexpected error in get_session_chunk", error=str(e), session_id=session_id, chunk_index=chunk_index)
        return _error_response("SESSION_ERROR", f"Unexpected error: {e}", {"session_id": session_id})


async def _handle_list_sessions(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle list_sessions tool call."""
    auth_tokens = arguments.get("auth_tokens")
    try:
        group = _resolve_group_from_tokens(auth_tokens)
    except Exception as e:
        if AuthError is not None and isinstance(e, AuthError):
            return _error_response("AUTH_ERROR", str(e))
        raise

    try:
        manager = get_session_manager()
        sessions = manager.list_sessions(group=group)
        return [_json_text({"sessions": sessions, "total": len(sessions)})]
    except GofrDigError as e:
        return _exception_response(e)
    except Exception as e:
        logger.error("Unexpected error in list_sessions", error=str(e))
        return _error_response("SESSION_ERROR", f"Unexpected error: {e}")


def _resolve_web_base_url(override: str | None = None) -> str:
    """Resolve the web server base URL for chunk URLs.

    Priority: explicit override → GOFR_DIG_WEB_URL env var → localhost default.
    """
    import os

    if override:
        return override.rstrip("/")

    env_url = os.environ.get("GOFR_DIG_WEB_URL")
    if env_url:
        return env_url.rstrip("/")

    web_port = os.environ.get("GOFR_DIG_WEB_PORT", "")
    if not web_port:
        return "http://localhost"
    return f"http://localhost:{web_port}"


async def _handle_get_session_urls(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_session_urls tool call.

    Returns a list of HTTP URLs for every chunk in a session so that
    automation services (N8N, Make, etc.) can iterate and GET each chunk.
    """
    session_id = arguments.get("session_id")
    if not session_id:
        return _error_response("INVALID_ARGUMENT", "session_id is required")

    auth_tokens = arguments.get("auth_tokens")
    try:
        group = _resolve_group_from_tokens(auth_tokens)
    except Exception as e:
        if AuthError is not None and isinstance(e, AuthError):
            return _error_response("AUTH_ERROR", str(e))
        raise

    base_url = _resolve_web_base_url(arguments.get("base_url"))

    try:
        manager = get_session_manager()
        info = manager.get_session_info(session_id, group=group)
        total_chunks = info["total_chunks"]

        chunk_urls = [
            f"{base_url}/sessions/{session_id}/chunks/{i}"
            for i in range(total_chunks)
        ]

        return [
            _json_text(
                {
                    "success": True,
                    "session_id": session_id,
                    "url": info.get("url", ""),
                    "total_chunks": total_chunks,
                    "chunk_urls": chunk_urls,
                }
            )
        ]
    except Exception as e:
        if PermissionDeniedError is not None and isinstance(e, PermissionDeniedError):
            return _error_response("PERMISSION_DENIED", str(e), {"session_id": session_id})
        if isinstance(e, GofrDigError):
            return _exception_response(e)
        logger.error(
            "Unexpected error in get_session_urls",
            error=str(e),
            session_id=session_id,
        )
        return _error_response(
            "SESSION_ERROR", f"Unexpected error: {e}", {"session_id": session_id}
        )


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


async def main(host: str = "0.0.0.0", port: int = 0) -> None:
    """Run the server."""
    import uvicorn

    if port == 0:
        port = int(os.environ["GOFR_DIG_MCP_PORT"])

    config = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
