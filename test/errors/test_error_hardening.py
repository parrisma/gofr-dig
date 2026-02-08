"""Tests to validate the error hardening implemented in Phases 1–7.

Covers:
1. SessionManager raises correct typed exceptions
2. MCP tool handlers return correct error codes
3. Fetch/extraction error classifiers produce correct codes
4. All error responses include recovery_strategy
5. RECOVERY_STRATEGIES coverage audit
"""

import json
import pytest
from typing import Any, List
from unittest.mock import MagicMock, patch

from app.exceptions import SessionNotFoundError, SessionValidationError
from app.errors.mapper import RECOVERY_STRATEGIES, error_to_mcp_response, error_to_web_response
from app.scraping.fetcher import FetchResult
from app.mcp_server.mcp_server import (
    _classify_fetch_error,
    _classify_extraction_error,
    _error_response,
)


def get_mcp_result_data(result: Any) -> dict:
    """Extract JSON data from MCP tool result."""
    result_list: List[Any] = result
    return json.loads(result_list[0].text)


# ---------------------------------------------------------------------------
# 1. SessionManager raises correct typed exceptions
# ---------------------------------------------------------------------------

class TestSessionManagerExceptions:
    """Verify SessionManager raises typed exceptions (Phase 1)."""

    def test_session_not_found_raises_session_not_found_error(self, tmp_path):
        from app.session.manager import SessionManager

        manager = SessionManager(tmp_path)
        with pytest.raises(SessionNotFoundError) as exc_info:
            manager.get_session_info("nonexistent-id")
        assert exc_info.value.code == "SESSION_NOT_FOUND"

    def test_invalid_chunk_index_raises_session_validation_error(self, tmp_path):
        from app.session.manager import SessionManager

        manager = SessionManager(tmp_path)
        sid = manager.create_session(
            content={"text": "hello world", "url": "http://example.com"},
            url="http://example.com",
            chunk_size=4000,
        )
        with pytest.raises(SessionValidationError) as exc_info:
            manager.get_chunk(sid, 999)
        assert exc_info.value.code == "INVALID_CHUNK_INDEX"

    def test_session_not_found_has_details(self, tmp_path):
        from app.session.manager import SessionManager

        manager = SessionManager(tmp_path)
        with pytest.raises(SessionNotFoundError) as exc_info:
            manager.get_session_info("abc-123")
        assert exc_info.value.details.get("session_id") == "abc-123"


# ---------------------------------------------------------------------------
# 2. Fetch error classifier
# ---------------------------------------------------------------------------

class TestClassifyFetchError:
    """Verify _classify_fetch_error maps status codes correctly (Phase 4)."""

    def _make_result(self, status_code: int = 0, error: str = "",
                     rate_limited: bool = False) -> FetchResult:
        return FetchResult(
            url="http://example.com",
            status_code=status_code,
            content="",
            error=error or None,
            rate_limited=rate_limited,
        )

    def test_404_returns_url_not_found(self):
        assert _classify_fetch_error(self._make_result(404, "Not Found")) == "URL_NOT_FOUND"

    def test_403_returns_access_denied(self):
        assert _classify_fetch_error(self._make_result(403, "Forbidden")) == "ACCESS_DENIED"

    def test_429_returns_rate_limited(self):
        assert _classify_fetch_error(self._make_result(429, "Too Many Requests")) == "RATE_LIMITED"

    def test_rate_limited_flag_returns_rate_limited(self):
        assert _classify_fetch_error(
            self._make_result(200, "error", rate_limited=True)
        ) == "RATE_LIMITED"

    def test_500_returns_fetch_error(self):
        assert _classify_fetch_error(self._make_result(500, "Internal Server Error")) == "FETCH_ERROR"

    def test_502_returns_fetch_error(self):
        assert _classify_fetch_error(self._make_result(502, "Bad Gateway")) == "FETCH_ERROR"

    def test_timeout_in_error_returns_timeout_error(self):
        assert _classify_fetch_error(self._make_result(0, "Connection timed out")) == "TIMEOUT_ERROR"

    def test_timeout_keyword_returns_timeout_error(self):
        assert _classify_fetch_error(self._make_result(0, "Request timeout")) == "TIMEOUT_ERROR"

    def test_connection_refused_returns_connection_error(self):
        assert _classify_fetch_error(
            self._make_result(0, "Connection refused")
        ) == "CONNECTION_ERROR"

    def test_dns_resolve_returns_connection_error(self):
        assert _classify_fetch_error(
            self._make_result(0, "Could not resolve host")
        ) == "CONNECTION_ERROR"

    def test_unknown_error_returns_fetch_error(self):
        assert _classify_fetch_error(self._make_result(0, "Something weird")) == "FETCH_ERROR"


# ---------------------------------------------------------------------------
# 3. Extraction error classifier
# ---------------------------------------------------------------------------

class TestClassifyExtractionError:
    """Verify _classify_extraction_error maps error strings correctly (Phase 5)."""

    def test_selector_not_found(self):
        assert _classify_extraction_error(
            "Selector '#main' did not match any elements"
        ) == "SELECTOR_NOT_FOUND"

    def test_invalid_selector(self):
        assert _classify_extraction_error(
            "Invalid selector '###': pseudo-element"
        ) == "INVALID_SELECTOR"

    def test_encoding_error(self):
        assert _classify_extraction_error(
            "encoding error: cannot decode bytes"
        ) == "ENCODING_ERROR"

    def test_decode_error(self):
        assert _classify_extraction_error(
            "Failed to decode response body"
        ) == "ENCODING_ERROR"

    def test_generic_extraction_error(self):
        assert _classify_extraction_error("Something went wrong") == "EXTRACTION_ERROR"

    def test_empty_string_returns_extraction_error(self):
        assert _classify_extraction_error("") == "EXTRACTION_ERROR"


# ---------------------------------------------------------------------------
# 4. MCP tool handlers return correct error codes
# ---------------------------------------------------------------------------

class TestMCPToolErrorCodes:
    """Verify MCP tool handlers return structured error codes (Phase 2/4/5)."""

    @pytest.mark.asyncio
    async def test_get_session_info_missing_session_returns_error(self):
        from app.mcp_server.mcp_server import handle_call_tool

        with patch("app.mcp_server.mcp_server.get_session_manager") as mock_mgr:
            manager = MagicMock()
            manager.get_session_info.side_effect = SessionNotFoundError(
                "SESSION_NOT_FOUND", "Session not found", {"session_id": "bad-id"}
            )
            mock_mgr.return_value = manager

            result = await handle_call_tool("get_session_info", {"session_id": "bad-id"})
            data = get_mcp_result_data(result)
            assert data["success"] is False
            assert "recovery_strategy" in data

    @pytest.mark.asyncio
    async def test_get_session_chunk_invalid_index_returns_error(self):
        from app.mcp_server.mcp_server import handle_call_tool

        with patch("app.mcp_server.mcp_server.get_session_manager") as mock_mgr:
            manager = MagicMock()
            manager.get_chunk.side_effect = SessionValidationError(
                "INVALID_CHUNK_INDEX", "Chunk index 99 out of range",
                {"chunk_index": 99, "total_chunks": 5}
            )
            mock_mgr.return_value = manager

            result = await handle_call_tool(
                "get_session_chunk", {"session_id": "s1", "chunk_index": 99}
            )
            data = get_mcp_result_data(result)
            assert data["success"] is False
            assert "recovery_strategy" in data

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_unknown_tool_code(self):
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool("nonexistent_tool", {})
        data = get_mcp_result_data(result)
        assert data["error_code"] == "UNKNOWN_TOOL"
        assert "recovery_strategy" in data

    @pytest.mark.asyncio
    async def test_get_content_missing_url_returns_invalid_url(self):
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool("get_content", {})
        data = get_mcp_result_data(result)
        assert data["error_code"] == "INVALID_URL"
        assert "recovery_strategy" in data

    @pytest.mark.asyncio
    async def test_get_structure_missing_url_returns_invalid_url(self):
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool("get_structure", {})
        data = get_mcp_result_data(result)
        assert data["error_code"] == "INVALID_URL"
        assert "recovery_strategy" in data


# ---------------------------------------------------------------------------
# 5. _error_response always includes recovery_strategy
# ---------------------------------------------------------------------------

class TestErrorResponseStructure:
    """Verify _error_response produces complete, structured responses."""

    @pytest.mark.parametrize("error_code", list(RECOVERY_STRATEGIES.keys()))
    def test_error_response_includes_recovery_for_known_codes(self, error_code):
        result = _error_response(error_code, f"Test error for {error_code}")
        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["error_code"] == error_code
        assert "recovery_strategy" in data
        # Should use the mapped strategy, not the generic fallback
        assert data["recovery_strategy"] == RECOVERY_STRATEGIES[error_code]

    def test_error_response_unknown_code_has_fallback_recovery(self):
        result = _error_response("TOTALLY_UNKNOWN", "mystery error")
        data = json.loads(result[0].text)
        assert data["recovery_strategy"] == "Review the error message and try again."

    def test_error_response_includes_details_when_provided(self):
        result = _error_response("FETCH_ERROR", "fail", {"url": "http://x.com"})
        data = json.loads(result[0].text)
        assert data["details"] == {"url": "http://x.com"}


# ---------------------------------------------------------------------------
# 6. Error mapper produces correct web + MCP response shapes
# ---------------------------------------------------------------------------

class TestErrorMapperResponses:
    """Verify error_to_mcp_response and error_to_web_response shape."""

    def test_mcp_response_has_required_fields(self):
        err = SessionNotFoundError("SESSION_NOT_FOUND", "not found", {"session_id": "x"})
        resp = error_to_mcp_response(err)
        assert resp["success"] is False
        assert "error_code" in resp
        assert "message" in resp
        assert "recovery_strategy" in resp
        assert "details" in resp

    def test_web_response_has_nested_error_shape(self):
        err = SessionValidationError("INVALID_CHUNK_INDEX", "bad chunk", {"chunk_index": 5})
        resp = error_to_web_response(err)
        assert "error" in resp
        assert "code" in resp["error"]
        assert "message" in resp["error"]
        assert "recovery" in resp["error"]
        assert "details" in resp["error"]


# ---------------------------------------------------------------------------
# 7. RECOVERY_STRATEGIES coverage audit
# ---------------------------------------------------------------------------

class TestRecoveryStrategiesCoverage:
    """Verify RECOVERY_STRATEGIES entries are all reachable."""

    # Codes emitted via _error_response() calls in mcp_server.py
    DIRECTLY_EMITTED = {
        "UNKNOWN_TOOL", "INVALID_PROFILE", "INVALID_RATE_LIMIT",
        "INVALID_MAX_TOKENS", "INVALID_URL", "SESSION_ERROR",
        "INVALID_ARGUMENT", "ROBOTS_BLOCKED", "EXTRACTION_ERROR",
        "AUTH_ERROR", "PERMISSION_DENIED",
    }

    # Codes emitted via _classify_fetch_error()
    FETCH_CLASSIFIED = {
        "URL_NOT_FOUND", "ACCESS_DENIED", "RATE_LIMITED",
        "FETCH_ERROR", "TIMEOUT_ERROR", "CONNECTION_ERROR",
    }

    # Codes emitted via _classify_extraction_error()
    EXTRACTION_CLASSIFIED = {
        "SELECTOR_NOT_FOUND", "INVALID_SELECTOR", "ENCODING_ERROR",
        "EXTRACTION_ERROR",
    }

    # Codes that exist in strategies but aren't directly string-emitted
    # (they're either derived from class names or reserved for future use)
    KNOWN_UNLINKED = {
        "INVALID_HEADERS",       # No header validation exists yet
        "MAX_DEPTH_EXCEEDED",    # Depth is silently clamped, not errored
        "MAX_PAGES_EXCEEDED",    # Pages per level is silently clamped
        "INVALID_CHUNK_INDEX",   # Emitted by exception .code, not _error_response
        "SESSION_NOT_FOUND",     # Emitted by exception .code, not _error_response
        "CONFIGURATION_ERROR",   # Reserved for startup config errors
    }

    ALL_REACHABLE = DIRECTLY_EMITTED | FETCH_CLASSIFIED | EXTRACTION_CLASSIFIED

    def test_all_strategies_are_accounted_for(self):
        """Every RECOVERY_STRATEGIES key should be either reachable or known-unlinked."""
        all_codes = set(RECOVERY_STRATEGIES.keys())
        accounted = self.ALL_REACHABLE | self.KNOWN_UNLINKED
        unaccounted = all_codes - accounted
        assert not unaccounted, f"Unaccounted RECOVERY_STRATEGIES codes: {unaccounted}"

    def test_no_reachable_code_is_missing_strategy(self):
        """Every code emitted by classifiers/handlers should have a strategy."""
        for code in self.ALL_REACHABLE:
            assert code in RECOVERY_STRATEGIES, f"Emitted code {code} has no RECOVERY_STRATEGY"
