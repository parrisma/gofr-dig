import pytest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient
from app.web_server.web_server import GofrDigWebServer
from app.session.manager import SessionManager
from app.exceptions import SessionNotFoundError, SessionValidationError

@pytest.fixture
def mock_session_manager():
    manager = MagicMock(spec=SessionManager)
    manager.get_session_info.return_value = {
        "session_id": "mock-session-id",
        "total_chunks": 5,
        "chunk_size": 1000,
        "url": "http://example.com",
        "total_size_bytes": 5000,
        "created_at": "2025-01-01T00:00:00Z",
        "group": "test-group"
    }
    manager.get_chunk.return_value = "Mock chunk content"
    return manager

@pytest.fixture
def client(mock_session_manager):
    with patch("app.web_server.web_server.SessionManager", return_value=mock_session_manager):
        server = GofrDigWebServer()
        # Inject mock manager directly to be sure
        server.session_manager = mock_session_manager
        return TestClient(server.get_app())

def test_get_session_info(client, mock_session_manager):
    response = client.get("/sessions/mock-session-id/info")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "mock-session-id"
    assert data["total_chunks"] == 5
    mock_session_manager.get_session_info.assert_called_with("mock-session-id")

def test_get_session_chunk(client, mock_session_manager):
    response = client.get("/sessions/mock-session-id/chunks/0")
    assert response.status_code == 200
    assert response.text == "Mock chunk content"
    mock_session_manager.get_chunk.assert_called_with("mock-session-id", 0)

def test_get_session_info_not_found(client, mock_session_manager):
    mock_session_manager.get_session_info.side_effect = SessionNotFoundError(
        "SESSION_NOT_FOUND", "Session not found", {"session_id": "invalid-id"}
    )
    response = client.get("/sessions/invalid-id/info")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "SESSION_NOT_FOUND"

def test_get_session_chunk_not_found(client, mock_session_manager):
    mock_session_manager.get_chunk.side_effect = SessionNotFoundError(
        "SESSION_NOT_FOUND", "Session not found", {"session_id": "mock-session-id"}
    )
    response = client.get("/sessions/mock-session-id/chunks/99")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "SESSION_NOT_FOUND"

def test_get_session_chunk_invalid_index(client, mock_session_manager):
    mock_session_manager.get_chunk.side_effect = SessionValidationError(
        "INVALID_CHUNK_INDEX", "Chunk index 99 out of range", {"chunk_index": 99, "total_chunks": 5}
    )
    response = client.get("/sessions/mock-session-id/chunks/99")
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "SESSION_VALIDATION"


# ==========================================================================
# get_session_urls endpoint
# ==========================================================================

def test_get_session_urls(client, mock_session_manager):
    """Returns chunk URLs for a valid session."""
    response = client.get("/sessions/mock-session-id/urls")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["session_id"] == "mock-session-id"
    assert data["total_chunks"] == 5
    assert len(data["chunk_urls"]) == 5
    # Each URL should contain the session ID and a chunk index
    for i, url in enumerate(data["chunk_urls"]):
        assert f"/sessions/mock-session-id/chunks/{i}" in url


def test_get_session_urls_base_url_override(client, mock_session_manager):
    """base_url query param overrides auto-detection."""
    response = client.get("/sessions/mock-session-id/urls?base_url=https://my-proxy.example.com")
    assert response.status_code == 200
    data = response.json()
    assert all(
        url.startswith("https://my-proxy.example.com/sessions/")
        for url in data["chunk_urls"]
    )


def test_get_session_urls_not_found(client, mock_session_manager):
    """Returns 404 for unknown session."""
    mock_session_manager.get_session_info.side_effect = SessionNotFoundError(
        "SESSION_NOT_FOUND", "Session not found", {"session_id": "missing"}
    )
    response = client.get("/sessions/missing/urls")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "SESSION_NOT_FOUND"
