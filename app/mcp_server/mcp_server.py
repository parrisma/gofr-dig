#!/usr/bin/env python3
"""GOFR-DIG MCP Server."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from typing import Any, AsyncIterator, Dict, List
from urllib.parse import urlparse

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
from app.rate_limit import get_rate_limiter

try:
    from gofr_common.auth.exceptions import AuthError
except ImportError:
    AuthError = None  # type: ignore[assignment,misc]

try:
    from gofr_common.storage.exceptions import PermissionDeniedError
except ImportError:
    PermissionDeniedError = None  # type: ignore[assignment,misc]

# Shared auth_token schema fragment — added to every tool except ping.
AUTH_TOKEN_SCHEMA = {
    "auth_token": {
        "type": "string",
        "description": (
            "JWT token for authentication. "
            "The server verifies the token and uses the first group "
            "to scope session access. "
            "Omit for anonymous/public access."
        ),
    },
}

# Module-level configuration (set by main_mcp.py)
auth_service: Any = None


def _resolve_group_from_token(auth_token: str | None) -> str | None:
    """Resolve the primary group from an auth_token passed as a tool parameter.

    Returns the first group from the token, or None if
    auth is disabled or no token provided.

    Raises AuthError if a token is provided but invalid.
    """
    if auth_service is None:
        return None  # auth disabled (--no-auth)

    if not auth_token:
        return None  # anonymous → public

    raw_token = auth_token
    # Strip "Bearer " prefix if present
    if raw_token.lower().startswith("bearer "):
        raw_token = raw_token[7:].strip()
    else:
        raw_token = raw_token.strip()

    if not raw_token:
        return None  # empty string → anonymous

    token_info = auth_service.verify_token(raw_token)
    if token_info.groups:
        return token_info.groups[0]  # primary group = first in list
    return None  # valid token, no groups → anonymous


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
3. get_content — fetch and extract text. For a single page use depth=1 (default). For documentation sites use depth=2 or 3. Set session=true to store results server-side; by default content is returned inline.
4. If session=true was set and a session_id is returned, retrieve content with get_session_chunk(session_id, chunk_index) iterating chunk_index from 0 to total_chunks-1. Use get_session_info to check session metadata.
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


def _safe_url_host(url: Any) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    try:
        return urlparse(url).netloc or None
    except Exception:
        return None


def _tool_invoked_message(name: str, arguments: Dict[str, Any]) -> str:
    """Build a human-readable message for tool invocation logs.

    The message is what SEQ / operators see first, so it must
    answer: *what* tool, *against what target*, with *which key params*.
    """
    url = arguments.get("url") or ""
    host = _safe_url_host(url)
    sid = arguments.get("session_id")
    depth = arguments.get("depth")

    parts = [name]
    if host:
        parts.append(host)
    elif sid:
        parts.append(f"session={sid}")
    if depth and int(depth) > 1:
        parts.append(f"depth={depth}")
    if arguments.get("session"):
        parts.append("session_mode")
    if arguments.get("selector"):
        parts.append(f"selector={arguments['selector'][:40]}")

    return " | ".join(parts)


def _tool_args_summary(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    request_id = arguments.get("request_id")
    session_id = arguments.get("session_id")
    url = arguments.get("url", "")
    summary: Dict[str, Any] = {
        "event": "tool_invoked",
        "tool": name,
        "operation": name,
        "stage": "invoke",
        "dependency": "mcp",
        "request_id": request_id,
        "session_id": session_id,
        "url": url if url else None,
        "selector_present": bool(arguments.get("selector")),
        "depth": arguments.get("depth"),
        "session_mode": bool(arguments.get("session")),
        "timeout_seconds": arguments.get("timeout_seconds"),
        "max_chars": arguments.get("max_chars"),
        "group": arguments.get("group"),
        "url_host": _safe_url_host(url),
    }
    return {k: v for k, v in summary.items() if v is not None}


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
    if "private" in error_str and "internal" in error_str:
        return "SSRF_BLOCKED"
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
    logger.warning(
        "Tool exception", error_code=response["error_code"], error_message=response["message"]
    )
    return [_json_text(response)]


def _truncate_to_chars(text: str, max_chars: int) -> tuple[str, bool]:
    """Truncate text to fit within character limit.

    Args:
        text: Text to truncate
        max_chars: Maximum characters allowed

    Returns:
        Tuple of (truncated_text, was_truncated)
    """
    if len(text) <= max_chars:
        return text, False

    # Truncate and try to end at a sentence or word boundary
    truncated = text[:max_chars]

    # Try to find a sentence ending
    last_period = truncated.rfind(". ")
    last_newline = truncated.rfind("\n")
    break_point = max(last_period, last_newline)

    if break_point > max_chars * 0.8:  # Only use if we keep at least 80%
        truncated = truncated[: break_point + 1]

    return truncated.rstrip() + "\n\n[Content truncated due to size limit]", True


def _apply_char_limit(page_data: Dict[str, Any], max_chars: int) -> tuple[Dict[str, Any], bool]:
    """Apply character limit to a single page's content.

    Args:
        page_data: Page data dictionary with 'text' field
        max_chars: Maximum characters allowed

    Returns:
        Tuple of (modified_page_data, was_truncated)
    """
    if not page_data.get("success", False):
        return page_data, False

    text = page_data.get("text", "")
    if not text:
        return page_data, False

    truncated_text, was_truncated = _truncate_to_chars(text, max_chars)
    if was_truncated:
        page_data = page_data.copy()
        page_data["text"] = truncated_text
        page_data["truncated"] = True
        page_data["original_chars"] = len(text)
        page_data["returned_chars"] = len(truncated_text)

    return page_data, was_truncated


def _apply_char_limit_multipage(
    results: Dict[str, Any], max_chars: int
) -> tuple[Dict[str, Any], bool]:
    """Apply character limit across multi-page crawl results.

    Truncates pages in reverse order (deepest first) to preserve most important content.

    Args:
        results: Multi-page results with 'pages' array and root 'text'
        max_chars: Maximum characters allowed

    Returns:
        Tuple of (modified_results, was_truncated)
    """
    # Calculate total characters across all content
    root_text = results.get("text", "") or ""
    root_chars = len(root_text)

    pages = results.get("pages", [])
    page_chars = [len(p.get("text", "") or "") for p in pages]
    total_chars = root_chars + sum(page_chars)

    if total_chars <= max_chars:
        return results, False

    # Need to truncate - work backwards from deepest pages
    results = results.copy()
    results["pages"] = [p.copy() for p in pages]
    results["truncated"] = True
    results["original_chars"] = total_chars

    chars_to_remove = total_chars - max_chars
    pages_removed = 0
    pages_truncated = 0

    # First, try removing pages from the end (deepest first)
    while chars_to_remove > 0 and results["pages"]:
        last_page = results["pages"][-1]
        last_page_chars = len(last_page.get("text", "") or "")

        if last_page_chars <= chars_to_remove:
            # Remove entire page
            results["pages"].pop()
            chars_to_remove -= last_page_chars
            pages_removed += 1
        else:
            # Truncate this page's text
            remaining_chars = last_page_chars - chars_to_remove
            if remaining_chars < 2000:  # Too small, remove it
                results["pages"].pop()
                chars_to_remove -= last_page_chars
                pages_removed += 1
            else:
                truncated_text, _ = _truncate_to_chars(last_page.get("text", ""), remaining_chars)
                results["pages"][-1]["text"] = truncated_text
                results["pages"][-1]["truncated"] = True
                pages_truncated += 1
                chars_to_remove = 0

    # If still over, truncate root text
    if chars_to_remove > 0 and root_text:
        remaining_root_chars = root_chars - chars_to_remove
        if remaining_root_chars > 2000:
            truncated_text, _ = _truncate_to_chars(root_text, remaining_root_chars)
            results["text"] = truncated_text

    # Update summary
    results["returned_chars"] = max_chars
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
                idempotentHint=True,
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
                "- rate_limit_delay (default 1.0s, range 0\u201360) \u2014 pause between requests.\n"
                "- max_response_chars (default 400000, range 4000\u20134000000) \u2014 cap response size in characters. "
                "Content exceeding this is truncated (deepest pages removed first).\n\n"
                "robots.txt is always respected and cannot be disabled.\n\n"
                "Returns: {success, profile, rate_limit_delay, max_response_chars}.\n"
                "Errors: INVALID_PROFILE, INVALID_RATE_LIMIT, INVALID_MAX_RESPONSE_CHARS."
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
                        "description": 'Custom HTTP headers (only used with profile=\'custom\'). Example: {"Accept-Language": "en-US"}',
                        "additionalProperties": {"type": "string"},
                    },
                    "custom_user_agent": {
                        "type": "string",
                        "description": "Custom User-Agent string (only used with profile='custom').",
                    },
                    "rate_limit_delay": {
                        "type": "number",
                        "description": "Seconds between requests (default: 1.0, range 0\u201360). Increase if you see rate-limit errors.",
                        "minimum": 0,
                    },
                    "max_response_chars": {
                        "type": "integer",
                        "description": "Max response size in characters (default: 400000). Reduce for faster responses; increase to capture full large pages.",
                        "minimum": 4000,
                        "maximum": 4000000,
                        "default": 400000,
                    },
                    **AUTH_TOKEN_SCHEMA,
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
                "- depth=1 (default): scrape a single page.\n"
                "- depth=2: scrape the page AND the pages it links to.\n"
                "- depth=3: three levels deep (slow, use sparingly).\n\n"
                "SESSION MODE:\n"
                "- session=true: store results server-side and return a session_id. "
                "Use get_session(session_id) or get_session_chunk(session_id, chunk_index) to retrieve content.\n"
                "- session=false (default): return all content inline.\n"
                "All parameters are honored exactly as sent — no auto-overrides.\n\n"
                "PARSE MODE:\n"
                "- parse_results=true (default): crawl results are processed "
                "by the deterministic news parser. Returns structured stories with dedup, classification, "
                "and parse quality signals.\n"
                "- parse_results=false: returns raw crawl output (pages, text, links, etc).\n"
                "- Applies to all depths. For depth=1 the single page is wrapped and parsed.\n\n"
                "TIPS:\n"
                "- Call get_structure first to find a good CSS selector, then pass it as 'selector'.\n"
                "- Use include_links=false and include_meta=false if you only need text.\n"
                "- If you get ROBOTS_BLOCKED, choose a URL/path allowed by robots.txt.\n"
                "- If you get FETCH_ERROR, try set_antidetection with profile='stealth' or 'browser_tls'.\n\n"
                "Errors: INVALID_URL, FETCH_ERROR, ROBOTS_BLOCKED, EXTRACTION_ERROR, "
                "MAX_DEPTH_EXCEEDED, MAX_PAGES_EXCEEDED, PARSE_ERROR."
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
                            "Crawl depth. 1 = single page. "
                            "2 = page + its linked pages. 3 = two levels of links. "
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
                            "Control session storage. true = store server-side and return a session_id. "
                            "false (default) = return all content inline. "
                            "Parameters are honored exactly — no auto-override."
                        ),
                        "default": False,
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
                    "max_bytes": {
                        "type": "integer",
                        "description": (
                            "Maximum allowed response size in bytes for inline content. "
                            "If the response exceeds this limit, returns CONTENT_TOO_LARGE error. "
                            "Default: 5242880 (5 MB)."
                        ),
                        "default": 5242880,
                    },
                    "timeout_seconds": {
                        "type": "number",
                        "description": "Per-request fetch timeout in seconds (default 60).",
                        "minimum": 1,
                        "default": 60,
                    },
                    "parse_results": {
                        "type": "boolean",
                        "description": (
                            "Run the deterministic news parser on crawl results. "
                            "Returns a structured feed with deduplicated stories, sections, "
                            "provenance, and parse-quality signals instead of raw page data. "
                            "Applies to all depths. Default true."
                        ),
                        "default": True,
                    },
                    "source_profile_name": {
                        "type": "string",
                        "description": (
                            "Source profile for the news parser (e.g. 'scmp'). "
                            "Controls site-specific date patterns, section labels, "
                            "and noise markers. Omit to use the generic fallback "
                            "profile. Only used when parse_results=true."
                        ),
                    },
                    **AUTH_TOKEN_SCHEMA,
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
                    "selector": {
                        "type": "string",
                        "description": (
                            "CSS selector to scope the analysis to a specific part of the page. "
                            "Examples: '#main-content', 'article', '.post-body'. "
                            "Omit to analyze the full page."
                        ),
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
                    "timeout_seconds": {
                        "type": "number",
                        "description": "Per-request fetch timeout in seconds (default 60).",
                        "minimum": 1,
                        "default": 60,
                    },
                    **AUTH_TOKEN_SCHEMA,
                },
                "required": ["url"],
            },
            annotations=ToolAnnotations(
                title="Get Structure",
                readOnlyHint=True,
                idempotentHint=True,
                openWorldHint=True,
            ),
        ),
        Tool(
            name="get_session_info",
            description=(
                "Get metadata for a stored scraping session. "
                "Returns: {success, session_id, url, total_chunks, total_size, created_at}.\n\n"
                "Use this to check how many chunks a session has and its total size. "
                "The session_id comes from a previous get_content call with session=true.\n\n"
                "NEXT STEPS: Call get_session(session_id) to get the full text, "
                "or get_session_chunk(session_id, chunk_index) for one chunk at a time.\n\n"
                "Errors: SESSION_NOT_FOUND."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session GUID returned by get_content when session storage was used.",
                    },
                    **AUTH_TOKEN_SCHEMA,
                },
                "required": ["session_id"],
            },
            annotations=ToolAnnotations(
                title="Get Session Info",
                readOnlyHint=True,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="get_session_chunk",
            description=(
                "Retrieve one chunk of text from a stored session. "
                "Returns: {success, session_id, chunk_index, total_chunks, content}.\n\n"
                "To read all content: iterate chunk_index from 0 to total_chunks-1. "
                "Get total_chunks from get_session_info or from the get_content response that created the session.\n\n"
                "TIP: Prefer get_session(session_id) if you need all chunks at once "
                "and the total size is under 5 MB.\n\n"
                "Errors: SESSION_NOT_FOUND, CHUNK_NOT_FOUND."
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
                    **AUTH_TOKEN_SCHEMA,
                },
                "required": ["session_id", "chunk_index"],
            },
            annotations=ToolAnnotations(
                title="Get Session Chunk",
                readOnlyHint=True,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="list_sessions",
            description=(
                "List all stored scraping sessions. "
                "Returns: {success, sessions: [{session_id, url, total_chunks, total_size, created_at}], total}.\n\n"
                "Use this to discover sessions from earlier scrapes. "
                "Returns an empty list (total=0) when no sessions exist.\n\n"
                "NEXT STEPS: Call get_session(session_id) to get full text, "
                "or get_session_info(session_id) for metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    **AUTH_TOKEN_SCHEMA,
                },
            },
            annotations=ToolAnnotations(
                title="List Sessions",
                readOnlyHint=True,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="get_session_urls",
            description=(
                "Get references to every chunk in a session.\n\n"
                "When as_json=true (default): returns {success, session_id, url, total_chunks, "
                "chunks: [{session_id, chunk_index}, ...]}.\n"
                "When as_json=false: returns {success, session_id, url, total_chunks, "
                "chunk_urls: [url, ...]}.\n\n"
                "The JSON format is ideal for MCP-based automation (N8N, agents) that will call "
                "get_session_chunk next. The URL format is for HTTP fan-out (Make, Zapier).\n\n"
                "TIP: If you just need the full content, use get_session(session_id) instead \u2014 "
                "it joins all chunks in one call.\n\n"
                "Typical flow: get_content(depth=2) \u2192 get_session_urls(session_id) "
                "\u2192 get_session_chunk for each chunk.\n\n"
                "Errors: SESSION_NOT_FOUND."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session GUID from a previous get_content call.",
                    },
                    "as_json": {
                        "type": "boolean",
                        "description": (
                            "If true (default), return a list of {session_id, chunk_index} objects. "
                            "If false, return a list of plain HTTP URLs for each chunk."
                        ),
                        "default": True,
                    },
                    "base_url": {
                        "type": "string",
                        "description": (
                            "Override the web-server base URL (e.g. 'http://myhost:PORT'). "
                            "Only used when as_json=false. "
                            "Auto-detected from GOFR_DIG_WEB_URL env or defaults to localhost if omitted."
                        ),
                    },
                    **AUTH_TOKEN_SCHEMA,
                },
                "required": ["session_id"],
            },
            annotations=ToolAnnotations(
                title="Get Session URLs",
                readOnlyHint=True,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="get_session",
            description=(
                "Retrieve and join ALL chunks of a session into a single text response. "
                "PREFERRED over iterating get_session_chunk when you need the full content.\n\n"
                "Returns: {success, session_id, url, total_chunks, total_size, content} "
                "with the full concatenated text.\n\n"
                "A max_bytes limit (default 5 MB) prevents returning excessively large content. "
                "If the session exceeds max_bytes, a CONTENT_TOO_LARGE error is returned with the "
                "actual size so you can fall back to get_session_chunk for chunk-by-chunk retrieval.\n\n"
                "Typical flow: get_content(url, depth=2) \u2192 get_session(session_id).\n\n"
                "Errors: SESSION_NOT_FOUND, CONTENT_TOO_LARGE."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session GUID from a previous get_content call.",
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": (
                            "Maximum allowed size in bytes for the joined content. "
                            "Returns an error if the session exceeds this limit. "
                            "Default: 5242880 (5 MB)."
                        ),
                        "default": 5242880,
                    },
                    "timeout_seconds": {
                        "type": "number",
                        "description": "Timeout in seconds for retrieving and joining chunks (default 60).",
                        "minimum": 1,
                        "default": 60,
                    },
                    **AUTH_TOKEN_SCHEMA,
                },
                "required": ["session_id"],
            },
            annotations=ToolAnnotations(
                title="Get Full Session",
                readOnlyHint=True,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
    ]


@app.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool invocations."""
    started = time.perf_counter()
    invocation_context = _tool_args_summary(name, arguments)
    invoked_msg = _tool_invoked_message(name, arguments)
    logger.info(
        f"tool.invoke {invoked_msg}",
        **invocation_context,
    )

    def _emit_completed(result: str, detail: str = "") -> None:
        duration_ms = int((time.perf_counter() - started) * 1000)
        host = invocation_context.get("url_host", "")
        target = f" {host}" if host else ""
        extra = f" — {detail}" if detail else ""
        logger.info(
            f"tool.done {name}{target} {result} {duration_ms}ms{extra}",
            event="tool_completed",
            tool=name,
            operation=name,
            stage="respond",
            dependency="mcp",
            result=result,
            duration_ms=duration_ms,
            request_id=invocation_context.get("request_id"),
            session_id=invocation_context.get("session_id"),
            url=invocation_context.get("url"),
            url_host=invocation_context.get("url_host"),
        )

    if name == "ping":
        from datetime import datetime, timezone

        from app.build_info import BUILD_NUMBER

        now = datetime.now(timezone.utc).astimezone()
        timestamp = now.strftime("%a %b %Y %H:%M:%S %Z")
        _emit_completed("success")
        return [
            _json_text(
                {
                    "status": "ok",
                    "service": "gofr-dig",
                    "build": BUILD_NUMBER,
                    "timestamp": timestamp,
                }
            )
        ]

    # Inbound rate limiting (skip for ping)
    auth_token = arguments.get("auth_token")
    identity: str | None = None
    try:
        identity = _resolve_group_from_token(auth_token)
    except Exception:
        pass  # auth errors handled by individual handlers
    limiter = get_rate_limiter()
    allowed, rate_info = limiter.check(identity)
    if not allowed:
        logger.warning(
            "Inbound rate limit exceeded",
            event="rate_limit_inbound_exceeded",
            operation=name,
            stage="auth",
            dependency="rate_limiter",
            result="denied",
            remediation="wait_for_rate_limit_window_reset",
            request_id=invocation_context.get("request_id"),
            group=identity,
        )
        _emit_completed("rate_limited")
        return _error_response(
            "RATE_LIMIT_EXCEEDED",
            f"Rate limit exceeded: {rate_info['limit']} calls per window. "
            f"Retry in {rate_info['reset_seconds']}s.",
            rate_info,
        )

    if name == "set_antidetection":
        result = await _handle_set_antidetection(arguments)
        _emit_completed("success")
        return result

    if name == "get_content":
        result = await _handle_get_content(arguments)
        _emit_completed("success")
        return result

    if name == "get_structure":
        result = await _handle_get_structure(arguments)
        _emit_completed("success")
        return result

    if name == "get_session_info":
        result = await _handle_get_session_info(arguments)
        _emit_completed("success")
        return result

    if name == "get_session_chunk":
        result = await _handle_get_session_chunk(arguments)
        _emit_completed("success")
        return result

    if name == "list_sessions":
        result = await _handle_list_sessions(arguments)
        _emit_completed("success")
        return result

    if name == "get_session_urls":
        result = await _handle_get_session_urls(arguments)
        _emit_completed("success")
        return result

    if name == "get_session":
        result = await _handle_get_session(arguments)
        _emit_completed("success")
        return result

    _emit_completed("unknown_tool")
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

    if "rate_limit_delay" in arguments:
        delay = arguments["rate_limit_delay"]
        if delay < 0:
            return _error_response(
                "INVALID_RATE_LIMIT",
                "rate_limit_delay must be non-negative",
                {"provided_value": delay},
            )
        state.rate_limit_delay = delay

    if "max_response_chars" in arguments:
        max_response_chars = arguments["max_response_chars"]
        if max_response_chars < 4000:
            return _error_response(
                "INVALID_MAX_RESPONSE_CHARS",
                "max_response_chars must be at least 4000",
                {"provided_value": max_response_chars},
            )
        if max_response_chars > 4000000:
            return _error_response(
                "INVALID_MAX_RESPONSE_CHARS",
                "max_response_chars cannot exceed 4000000",
                {"provided_value": max_response_chars},
            )
        state.max_response_chars = max_response_chars

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
        "respect_robots_txt": True,
        "rate_limit_delay": state.rate_limit_delay,
        "max_response_chars": state.max_response_chars,
    }

    if profile == AntiDetectionProfile.CUSTOM:
        response["custom_headers"] = state.custom_headers
        if state.custom_user_agent:
            response["custom_user_agent"] = state.custom_user_agent

    logger.info(
        f"antidetection.configured profile={profile.value}, "
        f"rate_limit_delay={state.rate_limit_delay}s, "
        f"max_response_chars={state.max_response_chars:,}",
        profile=profile.value,
        rate_limit_delay=state.rate_limit_delay,
        max_response_chars=state.max_response_chars,
    )
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
    max_bytes = arguments.get("max_bytes", 5_242_880)  # 5 MB default
    timeout_seconds = arguments.get("timeout_seconds", 60)
    parse_results = arguments.get("parse_results", True)
    source_profile_name = arguments.get("source_profile_name")

    # When crawling (depth > 1), always extract links internally so we can
    # discover sub-pages.  The caller's include_links preference only controls
    # whether links appear in the *response*.
    extract_links = True if depth > 1 else include_links

    if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        return _error_response(
            "INVALID_ARGUMENT",
            "timeout_seconds must be a positive number",
            {"provided_value": timeout_seconds},
        )

    # Honor parameters exactly — no auto-overrides.
    # session defaults to false; caller must explicitly set session=true.

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
        fetch_result = await fetch_url(page_url, timeout_seconds=timeout_seconds)
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
                include_links=extract_links,
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

        # Always attach links to page_data so get_internal_links() can
        # discover sub-pages during depth > 1 crawls.  We strip them from the
        # final response later if the caller set include_links=false.
        if extract_links and content.links:
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

        # Run news parser if requested
        if parse_results and page_data.get("success", True):
            try:
                from datetime import datetime, timezone

                from app.processing.news_parser import NewsParser

                parser_input = {
                    "start_url": url,
                    "pages": [page_data],
                    "crawl_time_utc": datetime.now(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "parser_version": "1.0.0",
                }
                if source_profile_name:
                    parser_input["source_profile_name"] = source_profile_name

                parser = NewsParser()
                parsed = parser.parse(parser_input)
                parsed["crawl_depth"] = depth
                page_data = parsed
            except Exception as exc:
                logger.error(
                    "news_parser_failed",
                    error=str(exc),
                    url=url,
                    depth=depth,
                )
                return _error_response(
                    "PARSE_ERROR",
                    f"News parser failed: {exc}",
                    {"url": url, "depth": depth},
                )

        # Handle session storage if requested
        if use_session:
            # Strip links before storing if caller didn't ask for them
            if not include_links:
                page_data.pop("links", None)

            manager = get_session_manager()
            # Use provided chunk_size or default to 4000
            c_size = chunk_size if chunk_size is not None else 4000

            # Resolve group from auth_token
            auth_token = arguments.get("auth_token")
            try:
                group = _resolve_group_from_token(auth_token)
            except Exception as e:
                if AuthError is not None and isinstance(e, AuthError):
                    return _error_response("AUTH_ERROR", str(e))
                raise

            try:
                session_id = manager.create_session(
                    url=url,
                    content=page_data,
                    chunk_size=c_size,
                    group=group,
                )

                # Get session info for response
                info = manager.get_session_info(session_id)

                return [
                    _json_text(
                        {
                            "success": True,
                            "response_type": "session",
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
                return _error_response(
                    "SESSION_ERROR", f"Failed to create session: {e}", {"url": url}
                )

        # Strip links the caller didn't ask for (raw mode only — parsed output has no links key)
        if not include_links and not parse_results:
            page_data.pop("links", None)

        # Apply character limit truncation (raw mode only)
        state = get_scraping_state()
        truncated = False
        if not parse_results:
            page_data, truncated = _apply_char_limit(page_data, state.max_response_chars)

        page_data["response_type"] = "inline"

        # Enforce max_bytes limit on serialized response
        serialized = json.dumps(page_data)
        if len(serialized.encode("utf-8")) > max_bytes:
            return _error_response(
                "CONTENT_TOO_LARGE",
                (
                    f"Inline response is {len(serialized.encode('utf-8')):,} bytes, "
                    f"exceeding max_bytes limit of {max_bytes:,}. "
                    f"Use session=true to store content server-side, "
                    f"or increase max_bytes."
                ),
                {"url": url, "max_bytes": max_bytes},
            )

        text_len = len(page_data.get("text", ""))
        links_n = len(page_data.get("links", []))
        host = _safe_url_host(url) or url
        logger.info(
            f"content.extracted {host} — {text_len:,} chars, {links_n} links"
            + (" [truncated]" if truncated else ""),
            url=url,
            text_length=text_len,
            links_count=links_n,
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
    crawl_host = _safe_url_host(url) or url
    logger.info(
        f"crawl.depth1 {crawl_host} — fetching root page",
        url=url,
        depth=1,
        max_pages_per_level=max_pages_per_level,
    )
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
        logger.info(
            f"crawl.depth2 {crawl_host} — fetching {len(current_level_links)} linked pages",
            url=url,
            depth=2,
            num_links=len(current_level_links),
        )
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
        logger.info(
            f"crawl.depth3 {crawl_host} — fetching {len(current_level_links)} linked pages",
            url=url,
            depth=3,
            num_links=len(current_level_links),
        )
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

    # Save crawl summary before potential parser replacement
    crawl_summary = results.get("summary", {})

    # Run news parser on multi-page results if requested
    if parse_results:
        try:
            from datetime import datetime, timezone

            from app.processing.news_parser import NewsParser

            results["crawl_time_utc"] = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            results["parser_version"] = "1.0.0"
            if source_profile_name:
                results["source_profile_name"] = source_profile_name

            parser = NewsParser()
            parsed = parser.parse(results)
            parsed["raw_summary"] = crawl_summary
            parsed["crawl_depth"] = depth
            results = parsed
        except Exception as exc:
            logger.error(
                "news_parser_failed",
                error=str(exc),
                url=url,
                depth=depth,
            )
            return _error_response(
                "PARSE_ERROR",
                f"News parser failed: {exc}",
                {"url": url, "depth": depth},
            )

    # Apply token limit truncation to multi-page results
    state = get_scraping_state()

    # Handle session storage if requested (same as depth=1)
    if use_session:
        # Strip links before storing if caller didn't ask for them (raw mode only)
        if not include_links and not parse_results:
            results.pop("links", None)
            for page in results.get("pages", []):
                page.pop("links", None)

        manager = get_session_manager()
        c_size = chunk_size if chunk_size is not None else 4000

        # Resolve group from auth_token
        auth_token = arguments.get("auth_token")
        try:
            group = _resolve_group_from_token(auth_token)
        except Exception as e:
            if AuthError is not None and isinstance(e, AuthError):
                return _error_response("AUTH_ERROR", str(e))
            raise

        try:
            session_id = manager.create_session(
                url=url,
                content=results,
                chunk_size=c_size,
                group=group,
            )
            info = manager.get_session_info(session_id)

            return [
                _json_text(
                    {
                        "success": True,
                        "response_type": "session",
                        "session_id": session_id,
                        "url": url,
                        "total_chunks": info["total_chunks"],
                        "total_size": info["total_size_bytes"],
                        "chunk_size": info["chunk_size"],
                        "created_at": info["created_at"],
                        "crawl_depth": depth,
                        "total_pages": crawl_summary.get("total_pages", 0),
                    }
                )
            ]
        except GofrDigError as e:
            return _exception_response(e)
        except Exception as e:
            logger.error("Failed to create session", error=str(e), url=url)
            return _error_response("SESSION_ERROR", f"Failed to create session: {e}", {"url": url})

    # Strip links the caller didn't ask for (raw mode only — parsed output has no pages/links)
    if not include_links and not parse_results:
        results.pop("links", None)
        for page in results.get("pages", []):
            page.pop("links", None)

    results["response_type"] = "inline"

    # Apply char limit truncation only to raw crawl results (parsed output has different shape)
    truncated = False
    if not parse_results:
        results, truncated = _apply_char_limit_multipage(results, state.max_response_chars)

    # Enforce max_bytes limit on serialized response
    serialized = json.dumps(results)
    if len(serialized.encode("utf-8")) > max_bytes:
        return _error_response(
            "CONTENT_TOO_LARGE",
            (
                f"Inline response is {len(serialized.encode('utf-8')):,} bytes, "
                f"exceeding max_bytes limit of {max_bytes:,}. "
                f"Use session=true to store content server-side, "
                f"or increase max_bytes."
            ),
            {"url": url, "max_bytes": max_bytes, "total_pages": crawl_summary.get("total_pages", 0)},
        )

    total_p = crawl_summary.get("total_pages", 0)
    total_t = crawl_summary.get("total_text_length", 0)
    logger.info(
        f"crawl.done {crawl_host} — {total_p} pages, {total_t:,} chars, depth={depth}"
        + (" [truncated]" if truncated else ""),
        start_url=url,
        depth=depth,
        total_pages=total_p,
        total_text_length=total_t,
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
    selector = arguments.get("selector")
    timeout_seconds = arguments.get("timeout_seconds", 60)

    if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        return _error_response(
            "INVALID_ARGUMENT",
            "timeout_seconds must be a positive number",
            {"provided_value": timeout_seconds},
        )

    # Fetch the URL
    fetch_result = await fetch_url(url, timeout_seconds=timeout_seconds)
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
    structure = analyzer.analyze(fetch_result.content, url=fetch_result.url, selector=selector)

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

    s_host = _safe_url_host(url) or url
    logger.info(
        f"structure.done {s_host} — {len(structure.sections)} sections, "
        f"{len(structure.internal_links)} internal + {len(structure.external_links)} external links",
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

    auth_token = arguments.get("auth_token")
    try:
        group = _resolve_group_from_token(auth_token)
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
        return _error_response(
            "SESSION_ERROR", f"Unexpected error: {e}", {"session_id": session_id}
        )


async def _handle_get_session_chunk(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_session_chunk tool call."""
    session_id = arguments.get("session_id")
    chunk_index = arguments.get("chunk_index")

    if not session_id:
        return _error_response("INVALID_ARGUMENT", "session_id is required")
    if chunk_index is None:
        return _error_response("INVALID_ARGUMENT", "chunk_index is required")

    auth_token = arguments.get("auth_token")
    try:
        group = _resolve_group_from_token(auth_token)
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
        logger.error(
            "Unexpected error in get_session_chunk",
            error=str(e),
            session_id=session_id,
            chunk_index=chunk_index,
        )
        return _error_response(
            "SESSION_ERROR", f"Unexpected error: {e}", {"session_id": session_id}
        )


async def _handle_list_sessions(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle list_sessions tool call."""
    auth_token = arguments.get("auth_token")
    try:
        group = _resolve_group_from_token(auth_token)
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

    auth_token = arguments.get("auth_token")
    try:
        group = _resolve_group_from_token(auth_token)
    except Exception as e:
        if AuthError is not None and isinstance(e, AuthError):
            return _error_response("AUTH_ERROR", str(e))
        raise

    as_json = arguments.get("as_json", True)
    base_url = _resolve_web_base_url(arguments.get("base_url"))

    try:
        manager = get_session_manager()
        info = manager.get_session_info(session_id, group=group)
        total_chunks = info["total_chunks"]

        response: Dict[str, Any] = {
            "success": True,
            "session_id": session_id,
            "url": info.get("url", ""),
            "total_chunks": total_chunks,
        }

        if as_json:
            response["chunks"] = [
                {"session_id": session_id, "chunk_index": i} for i in range(total_chunks)
            ]
        else:
            response["chunk_urls"] = [
                f"{base_url}/sessions/{session_id}/chunks/{i}" for i in range(total_chunks)
            ]

        return [_json_text(response)]
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


async def _handle_get_session(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_session tool call.

    Retrieves all chunks from a session, concatenates them, and returns
    the full content as a single text response.
    """
    session_id = arguments.get("session_id")
    if not session_id:
        return _error_response("INVALID_ARGUMENT", "session_id is required")

    max_bytes = arguments.get("max_bytes", 5_242_880)  # 5 MB default
    timeout_seconds = arguments.get("timeout_seconds", 60)

    auth_token = arguments.get("auth_token")
    try:
        group = _resolve_group_from_token(auth_token)
    except Exception as e:
        if AuthError is not None and isinstance(e, AuthError):
            return _error_response("AUTH_ERROR", str(e))
        raise

    try:
        manager = get_session_manager()
        info = manager.get_session_info(session_id, group=group)
        total_size = info.get("total_size_bytes", 0)

        if total_size > max_bytes:
            return _error_response(
                "CONTENT_TOO_LARGE",
                (
                    f"Session content is {total_size:,} bytes, "
                    f"exceeding max_bytes limit of {max_bytes:,}. "
                    f"Use get_session_chunk to retrieve chunks individually, "
                    f"or increase max_bytes."
                ),
                {
                    "session_id": session_id,
                    "total_size_bytes": total_size,
                    "max_bytes": max_bytes,
                    "total_chunks": info["total_chunks"],
                },
            )

        total_chunks = info["total_chunks"]
        parts = []

        async def _read_chunks():
            for i in range(total_chunks):
                chunk_text = manager.get_chunk(session_id, i, group=group)
                parts.append(chunk_text)

        try:
            await asyncio.wait_for(_read_chunks(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return _error_response(
                "TIMEOUT_ERROR",
                (
                    f"Timed out after {timeout_seconds}s reading {total_chunks} chunks. "
                    f"Use get_session_chunk for incremental retrieval, "
                    f"or increase timeout_seconds."
                ),
                {
                    "session_id": session_id,
                    "total_chunks": total_chunks,
                    "chunks_read": len(parts),
                    "timeout_seconds": timeout_seconds,
                },
            )

        content = "".join(parts)

        return [
            _json_text(
                {
                    "success": True,
                    "session_id": session_id,
                    "url": info.get("url", ""),
                    "total_chunks": total_chunks,
                    "total_size_bytes": len(content.encode("utf-8")),
                    "content": content,
                }
            )
        ]
    except Exception as e:
        if PermissionDeniedError is not None and isinstance(e, PermissionDeniedError):
            return _error_response("PERMISSION_DENIED", str(e), {"session_id": session_id})
        if isinstance(e, GofrDigError):
            return _exception_response(e)
        logger.error(
            "Unexpected error in get_session",
            error=str(e),
            session_id=session_id,
        )
        return _error_response(
            "SESSION_ERROR", f"Unexpected error: {e}", {"session_id": session_id}
        )


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
