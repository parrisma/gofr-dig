"""Tests for group-based session access control via MCP auth_tokens parameter.

Covers:
- Anonymous (no auth_tokens) → group=None
- Valid token → session tagged with group
- Group match → access allowed
- Group mismatch → PERMISSION_DENIED
- Multi-group tokens → first group used
- Invalid tokens → AUTH_ERROR
- Group-scoped listing
- No-auth mode (auth_service=None) → all sessions accessible
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from gofr_common.auth.exceptions import AuthError
from gofr_common.storage.exceptions import PermissionDeniedError

from app.mcp_server.mcp_server import (
    handle_call_tool,
    _resolve_group_from_tokens,
)
from app.session.manager import SessionManager
from conftest import _create_test_auth_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_manager_mock(group: str | None = "team-a") -> MagicMock:
    """Mock SessionManager with canned data."""
    mgr = MagicMock(spec=SessionManager)
    mgr.create_session.return_value = "mock-session-id"
    mgr.get_session_info.return_value = {
        "session_id": "mock-session-id",
        "total_chunks": 3,
        "chunk_size": 4000,
        "url": "http://example.com",
        "total_size_bytes": 9000,
        "total_chars": 9000,
        "created_at": "2025-01-01T00:00:00Z",
        "group": group,
    }
    mgr.get_chunk.return_value = "chunk data"
    mgr.list_sessions.return_value = [
        {
            "session_id": "s1",
            "url": "http://a.com",
            "created_at": "2025-01-01T00:00:00Z",
            "total_size_bytes": 100,
            "total_chars": 100,
            "total_chunks": 1,
            "chunk_size": 4000,
            "group": group,
        }
    ]
    return mgr


def _create_token(groups: list[str], auth_service=None) -> str:
    """Create a JWT for the given groups using the test auth service."""
    svc = auth_service or _create_test_auth_service()
    # Ensure the groups exist in the registry
    for g in groups:
        try:
            svc.groups.create_group(g, f"Test group {g}")
        except Exception:
            pass  # already exists (DuplicateGroupError)
    return svc.create_token(groups=groups, expires_in_seconds=3600)


# ---------------------------------------------------------------------------
# _resolve_group_from_tokens unit tests
# ---------------------------------------------------------------------------


class TestResolveGroupFromTokens:
    """Unit tests for the _resolve_group_from_tokens helper."""

    def test_none_when_auth_disabled(self):
        """auth_service=None (--no-auth) → always returns None."""
        with patch("app.mcp_server.mcp_server.auth_service", None):
            assert _resolve_group_from_tokens(["anything"]) is None

    def test_none_when_no_tokens(self):
        """No tokens provided → anonymous (None)."""
        svc = _create_test_auth_service()
        with patch("app.mcp_server.mcp_server.auth_service", svc):
            assert _resolve_group_from_tokens(None) is None
            assert _resolve_group_from_tokens([]) is None

    def test_returns_first_group(self):
        """Valid token with groups → returns first group."""
        svc = _create_test_auth_service()
        token = _create_token(["team-a", "team-b"], svc)
        with patch("app.mcp_server.mcp_server.auth_service", svc):
            result = _resolve_group_from_tokens([token])
            assert result == "team-a"

    def test_strips_bearer_prefix(self):
        """Bearer prefix is stripped before verification."""
        svc = _create_test_auth_service()
        token = _create_token(["team-x"], svc)
        with patch("app.mcp_server.mcp_server.auth_service", svc):
            result = _resolve_group_from_tokens([f"Bearer {token}"])
            assert result == "team-x"

    def test_invalid_token_raises_auth_error(self):
        """Invalid token → AuthError."""
        svc = _create_test_auth_service()
        with patch("app.mcp_server.mcp_server.auth_service", svc):
            with pytest.raises(AuthError):
                _resolve_group_from_tokens(["garbage-jwt"])

    def test_tries_next_on_auth_error(self):
        """If first token is bad but second is valid, uses second."""
        svc = _create_test_auth_service()
        good_token = _create_token(["team-ok"], svc)
        with patch("app.mcp_server.mcp_server.auth_service", svc):
            result = _resolve_group_from_tokens(["bad-token", good_token])
            assert result == "team-ok"


# ---------------------------------------------------------------------------
# MCP handler integration tests
# ---------------------------------------------------------------------------


class TestMCPSessionAuthHandlers:
    """Test auth_tokens parameter wiring in MCP session tool handlers."""

    @pytest.mark.asyncio
    async def test_no_auth_tokens_passes_none_group(self):
        """No auth_tokens → group=None passed to SessionManager."""
        mgr = _make_session_manager_mock(group=None)
        with patch("app.mcp_server.mcp_server.session_manager", mgr), \
             patch("app.mcp_server.mcp_server.auth_service", None):
            result = await handle_call_tool(
                "get_session_info",
                {"session_id": "s1"},
            )
            mgr.get_session_info.assert_called_with("s1", group=None)
            data = json.loads(result[0].text)  # type: ignore[index]
            assert data["session_id"] == "mock-session-id"

    @pytest.mark.asyncio
    async def test_valid_token_passes_group(self):
        """Valid auth_tokens → extracted group passed to SessionManager."""
        svc = _create_test_auth_service()
        token = _create_token(["team-a"], svc)
        mgr = _make_session_manager_mock(group="team-a")

        with patch("app.mcp_server.mcp_server.session_manager", mgr), \
             patch("app.mcp_server.mcp_server.auth_service", svc):
            await handle_call_tool(
                "get_session_info",
                {"session_id": "s1", "auth_tokens": [token]},
            )
            mgr.get_session_info.assert_called_with("s1", group="team-a")

    @pytest.mark.asyncio
    async def test_permission_denied_on_group_mismatch(self):
        """SessionManager raises PermissionDeniedError → PERMISSION_DENIED response."""
        svc = _create_test_auth_service()
        token = _create_token(["team-b"], svc)
        mgr = _make_session_manager_mock(group="team-a")
        mgr.get_session_info.side_effect = PermissionDeniedError("Access denied")

        with patch("app.mcp_server.mcp_server.session_manager", mgr), \
             patch("app.mcp_server.mcp_server.auth_service", svc):
            result = await handle_call_tool(
                "get_session_info",
                {"session_id": "s1", "auth_tokens": [token]},
            )
            data = json.loads(result[0].text)  # type: ignore[index]
            assert data["success"] is False
            assert data["error_code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_invalid_token_returns_auth_error(self):
        """Bad auth_tokens → AUTH_ERROR response."""
        svc = _create_test_auth_service()
        mgr = _make_session_manager_mock()

        with patch("app.mcp_server.mcp_server.session_manager", mgr), \
             patch("app.mcp_server.mcp_server.auth_service", svc):
            result = await handle_call_tool(
                "get_session_info",
                {"session_id": "s1", "auth_tokens": ["invalid-jwt"]},
            )
            data = json.loads(result[0].text)  # type: ignore[index]
            assert data["success"] is False
            assert data["error_code"] == "AUTH_ERROR"

    @pytest.mark.asyncio
    async def test_get_session_chunk_with_auth(self):
        """get_session_chunk passes group from token."""
        svc = _create_test_auth_service()
        token = _create_token(["team-c"], svc)
        mgr = _make_session_manager_mock(group="team-c")

        with patch("app.mcp_server.mcp_server.session_manager", mgr), \
             patch("app.mcp_server.mcp_server.auth_service", svc):
            await handle_call_tool(
                "get_session_chunk",
                {"session_id": "s1", "chunk_index": 0, "auth_tokens": [token]},
            )
            mgr.get_chunk.assert_called_with("s1", 0, group="team-c")

    @pytest.mark.asyncio
    async def test_get_session_chunk_permission_denied(self):
        """get_session_chunk with wrong group → PERMISSION_DENIED."""
        svc = _create_test_auth_service()
        token = _create_token(["team-b"], svc)
        mgr = _make_session_manager_mock()
        mgr.get_chunk.side_effect = PermissionDeniedError("Access denied")

        with patch("app.mcp_server.mcp_server.session_manager", mgr), \
             patch("app.mcp_server.mcp_server.auth_service", svc):
            result = await handle_call_tool(
                "get_session_chunk",
                {"session_id": "s1", "chunk_index": 0, "auth_tokens": [token]},
            )
            data = json.loads(result[0].text)  # type: ignore[index]
            assert data["error_code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_list_sessions_with_group(self):
        """list_sessions passes group to SessionManager."""
        svc = _create_test_auth_service()
        token = _create_token(["team-a"], svc)
        mgr = _make_session_manager_mock(group="team-a")

        with patch("app.mcp_server.mcp_server.session_manager", mgr), \
             patch("app.mcp_server.mcp_server.auth_service", svc):
            await handle_call_tool(
                "list_sessions",
                {"auth_tokens": [token]},
            )
            mgr.list_sessions.assert_called_once_with(group="team-a")

    @pytest.mark.asyncio
    async def test_list_sessions_anonymous(self):
        """list_sessions without tokens → group=None."""
        mgr = _make_session_manager_mock(group=None)
        with patch("app.mcp_server.mcp_server.session_manager", mgr), \
             patch("app.mcp_server.mcp_server.auth_service", None):
            await handle_call_tool("list_sessions", {})
            mgr.list_sessions.assert_called_once_with(group=None)

    @pytest.mark.asyncio
    async def test_get_session_urls_with_auth(self):
        """get_session_urls passes group from token."""
        svc = _create_test_auth_service()
        token = _create_token(["team-d"], svc)
        mgr = _make_session_manager_mock(group="team-d")

        with patch("app.mcp_server.mcp_server.session_manager", mgr), \
             patch("app.mcp_server.mcp_server.auth_service", svc):
            result = await handle_call_tool(
                "get_session_urls",
                {
                    "session_id": "s1",
                    "base_url": "http://web:8072",
                    "auth_tokens": [token],
                },
            )
            mgr.get_session_info.assert_called_with("s1", group="team-d")
            data = json.loads(result[0].text)  # type: ignore[index]
            assert data["success"] is True

    @pytest.mark.asyncio
    async def test_get_session_urls_permission_denied(self):
        """get_session_urls with wrong group → PERMISSION_DENIED."""
        svc = _create_test_auth_service()
        token = _create_token(["team-b"], svc)
        mgr = _make_session_manager_mock()
        mgr.get_session_info.side_effect = PermissionDeniedError("Access denied")

        with patch("app.mcp_server.mcp_server.session_manager", mgr), \
             patch("app.mcp_server.mcp_server.auth_service", svc):
            result = await handle_call_tool(
                "get_session_urls",
                {
                    "session_id": "s1",
                    "base_url": "http://web:8072",
                    "auth_tokens": [token],
                },
            )
            data = json.loads(result[0].text)  # type: ignore[index]
            assert data["error_code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_no_auth_mode_bypasses_tokens(self):
        """With auth_service=None, even invalid tokens are ignored."""
        mgr = _make_session_manager_mock(group=None)
        with patch("app.mcp_server.mcp_server.session_manager", mgr), \
             patch("app.mcp_server.mcp_server.auth_service", None):
            result = await handle_call_tool(
                "get_session_info",
                {"session_id": "s1", "auth_tokens": ["garbage"]},
            )
            # No AUTH_ERROR — auth_service is None so tokens are ignored
            mgr.get_session_info.assert_called_with("s1", group=None)
            data = json.loads(result[0].text)  # type: ignore[index]
            assert data["session_id"] == "mock-session-id"
