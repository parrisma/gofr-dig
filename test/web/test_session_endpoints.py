import pytest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient
from app.web_server.web_server import GofrDigWebServer
from app.session.manager import SessionManager

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
    mock_session_manager.get_session_info.side_effect = ValueError("Session not found")
    response = client.get("/sessions/invalid-id/info")
    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]

def test_get_session_chunk_not_found(client, mock_session_manager):
    mock_session_manager.get_chunk.side_effect = ValueError("Chunk not found")
    response = client.get("/sessions/mock-session-id/chunks/99")
    assert response.status_code == 404
    assert "Chunk not found" in response.json()["detail"]
