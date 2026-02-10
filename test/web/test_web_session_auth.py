"""Tests for group-based session access control via web Authorization header.

Covers:
- No Authorization header → group=None (anonymous)
- Valid Bearer token → group extracted, passed to SessionManager
- Wrong group → 403 PERMISSION_DENIED
- Invalid token → 401 AUTH_ERROR
- No-auth mode (auth_service=None) → all sessions accessible
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4
from starlette.testclient import TestClient

from gofr_common.storage.exceptions import PermissionDeniedError

from app.web_server.web_server import GofrDigWebServer
from app.session.manager import SessionManager
from conftest import _create_test_auth_service, _build_vault_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_auth_service():
    """Create an isolated test AuthService with a unique Vault path prefix."""
    vault_client = _build_vault_client()
    path_prefix = f"gofr/tests/{uuid4()}"
    return _create_test_auth_service(vault_client, path_prefix)

def _make_session_manager_mock(group: str | None = "team-a") -> MagicMock:
    mgr = MagicMock(spec=SessionManager)
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
    mgr.list_sessions.return_value = []
    return mgr


def _create_token(groups: list[str], auth_service=None) -> str:
    svc = auth_service or _make_auth_service()
    for g in groups:
        try:
            svc.groups.create_group(g, f"Test group {g}")
        except Exception:
            pass  # already exists (DuplicateGroupError)
    return svc.create_token(groups=groups, expires_in_seconds=3600)


def _make_client(
    auth_service=None,
    session_manager_mock=None,
) -> TestClient:
    """Create a TestClient with optional auth and mock session manager."""
    mock_mgr = session_manager_mock or _make_session_manager_mock()
    with patch("app.web_server.web_server.SessionManager", return_value=mock_mgr):
        server = GofrDigWebServer(auth_service=auth_service)
        server.session_manager = mock_mgr
        return TestClient(server.get_app())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWebSessionAuth:
    """Web server auth header → group scoping."""

    def test_no_header_passes_none_group(self):
        """No Authorization header → group=None."""
        mgr = _make_session_manager_mock(group=None)
        client = _make_client(auth_service=None, session_manager_mock=mgr)
        resp = client.get("/sessions/s1/info")
        assert resp.status_code == 200
        mgr.get_session_info.assert_called_with("s1", group=None)

    def test_valid_bearer_passes_group(self):
        """Valid Bearer token → group extracted and passed."""
        svc = _make_auth_service()
        token = _create_token(["team-a"], svc)
        mgr = _make_session_manager_mock(group="team-a")
        client = _make_client(auth_service=svc, session_manager_mock=mgr)

        resp = client.get(
            "/sessions/s1/info",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        mgr.get_session_info.assert_called_with("s1", group="team-a")

    def test_wrong_group_returns_403(self):
        """Token group ≠ session group → 403."""
        svc = _make_auth_service()
        token = _create_token(["team-b"], svc)
        mgr = _make_session_manager_mock(group="team-a")
        mgr.get_session_info.side_effect = PermissionDeniedError("Access denied")
        client = _make_client(auth_service=svc, session_manager_mock=mgr)

        resp = client.get(
            "/sessions/s1/info",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"]["code"] == "PERMISSION_DENIED"

    def test_invalid_token_returns_401(self):
        """Bad Bearer token → 401."""
        svc = _make_auth_service()
        mgr = _make_session_manager_mock()
        client = _make_client(auth_service=svc, session_manager_mock=mgr)

        resp = client.get(
            "/sessions/s1/info",
            headers={"Authorization": "Bearer garbage-jwt"},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "AUTH_ERROR"

    def test_chunk_with_valid_auth(self):
        """get_session_chunk passes group from header."""
        svc = _make_auth_service()
        token = _create_token(["team-c"], svc)
        mgr = _make_session_manager_mock(group="team-c")
        client = _make_client(auth_service=svc, session_manager_mock=mgr)

        resp = client.get(
            "/sessions/s1/chunks/0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        mgr.get_chunk.assert_called_with("s1", 0, group="team-c")

    def test_chunk_permission_denied(self):
        """get_session_chunk with wrong group → 403."""
        svc = _make_auth_service()
        token = _create_token(["team-b"], svc)
        mgr = _make_session_manager_mock()
        mgr.get_chunk.side_effect = PermissionDeniedError("Access denied")
        client = _make_client(auth_service=svc, session_manager_mock=mgr)

        resp = client.get(
            "/sessions/s1/chunks/0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"]["code"] == "PERMISSION_DENIED"

    def test_urls_with_valid_auth(self):
        """get_session_urls passes group from header."""
        svc = _make_auth_service()
        token = _create_token(["team-e"], svc)
        mgr = _make_session_manager_mock(group="team-e")
        client = _make_client(auth_service=svc, session_manager_mock=mgr)

        resp = client.get(
            "/sessions/s1/urls",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        mgr.get_session_info.assert_called_with("s1", group="team-e")

    def test_urls_permission_denied(self):
        """get_session_urls with wrong group → 403."""
        svc = _make_auth_service()
        token = _create_token(["team-b"], svc)
        mgr = _make_session_manager_mock()
        mgr.get_session_info.side_effect = PermissionDeniedError("Access denied")
        client = _make_client(auth_service=svc, session_manager_mock=mgr)

        resp = client.get(
            "/sessions/s1/urls",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"]["code"] == "PERMISSION_DENIED"

    def test_no_auth_mode_ignores_header(self):
        """auth_service=None → Authorization header ignored, group=None."""
        mgr = _make_session_manager_mock(group=None)
        client = _make_client(auth_service=None, session_manager_mock=mgr)

        resp = client.get(
            "/sessions/s1/info",
            headers={"Authorization": "Bearer garbage"},
        )
        assert resp.status_code == 200
        mgr.get_session_info.assert_called_with("s1", group=None)

    def test_chunk_invalid_token_returns_401(self):
        """get_session_chunk with bad token → 401."""
        svc = _make_auth_service()
        mgr = _make_session_manager_mock()
        client = _make_client(auth_service=svc, session_manager_mock=mgr)

        resp = client.get(
            "/sessions/s1/chunks/0",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401

    def test_urls_invalid_token_returns_401(self):
        """get_session_urls with bad token → 401."""
        svc = _make_auth_service()
        mgr = _make_session_manager_mock()
        client = _make_client(auth_service=svc, session_manager_mock=mgr)

        resp = client.get(
            "/sessions/s1/urls",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401
