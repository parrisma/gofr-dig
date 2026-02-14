import os
import pytest
import json
from unittest.mock import MagicMock, patch
from app.mcp_server.mcp_server import handle_call_tool, handle_list_tools
from app.session.manager import SessionManager
from app.scraping.fetcher import FetchResult

# Base URL for get_session_urls tests — derived from env (set by gofr_ports.env).
TEST_WEB_BASE_URL = "http://web:{}".format(os.environ.get("GOFR_DIG_WEB_PORT", os.environ.get("GOFR_DIG_WEB_PORT_TEST", "")))

@pytest.fixture
def mock_session_manager():
    manager = MagicMock(spec=SessionManager)
    manager.create_session.return_value = "mock-session-id"
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

@pytest.mark.asyncio
async def test_list_tools_includes_session_tools():
    tools = await handle_list_tools()  # type: ignore
    tool_names = [t.name for t in tools]
    assert "get_session_info" in tool_names
    assert "get_session_chunk" in tool_names
    assert "list_sessions" in tool_names
    
    # Check get_content has session param
    get_content = next(t for t in tools if t.name == "get_content")
    assert "session" in get_content.inputSchema["properties"]
    assert "chunk_size" in get_content.inputSchema["properties"]

@pytest.mark.asyncio
async def test_get_content_with_session(mock_session_manager):
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        # Mock fetch_url to return content
        with patch("app.mcp_server.mcp_server.fetch_url") as mock_fetch:
            mock_fetch.return_value = FetchResult(
                url="http://example.com",
                status_code=200,
                content="Some content",
                content_type="text/html",
                headers={},
                encoding="utf-8"
            )
            
            # Mock ContentExtractor
            with patch("app.scraping.extractor.ContentExtractor") as mock_extractor:
                mock_content = MagicMock()
                mock_content.success = True
                mock_content.url = "http://example.com"
                mock_content.title = "Test Page"
                mock_content.text = "Extracted text"
                mock_content.language = "en"
                mock_content.headings = []
                mock_content.links = []
                mock_content.images = []
                mock_content.meta = {}
                
                mock_extractor.return_value.extract.return_value = mock_content
                
                result = await handle_call_tool(
                    "get_content",
                    {"url": "http://example.com", "session": True, "parse_results": False}
                )
                
                # Verify session created
                mock_session_manager.create_session.assert_called_once()
                
                # Verify response contains session_id
                response = json.loads(result[0].text)  # type: ignore
                assert response["session_id"] == "mock-session-id"
                assert response["success"]

@pytest.mark.asyncio
async def test_get_session_info(mock_session_manager):
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool(
            "get_session_info",
            {"session_id": "mock-session-id"}
        )
        
        mock_session_manager.get_session_info.assert_called_with("mock-session-id", group=None)
        response = json.loads(result[0].text)  # type: ignore
        assert response["total_chunks"] == 5

@pytest.mark.asyncio
async def test_get_session_chunk(mock_session_manager):
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool(
            "get_session_chunk",
            {"session_id": "mock-session-id", "chunk_index": 0}
        )
        
        mock_session_manager.get_chunk.assert_called_with("mock-session-id", 0, group=None)
        response = json.loads(result[0].text)  # type: ignore
        assert response == "Mock chunk content"


@pytest.mark.asyncio
async def test_list_sessions(mock_session_manager):
    mock_session_manager.list_sessions.return_value = [
        {
            "session_id": "id-1",
            "url": "http://a.com",
            "created_at": "2025-01-01T00:00:00Z",
            "total_size_bytes": 1000,
            "total_chars": 1000,
            "total_chunks": 1,
            "chunk_size": 4000,
            "group": "test-group",
        },
        {
            "session_id": "id-2",
            "url": "http://b.com",
            "created_at": "2025-01-02T00:00:00Z",
            "total_size_bytes": 5000,
            "total_chars": 5000,
            "total_chunks": 2,
            "chunk_size": 4000,
            "group": "test-group",
        },
    ]

    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool("list_sessions", {})

        mock_session_manager.list_sessions.assert_called_once_with(group=None)
        response = json.loads(result[0].text)  # type: ignore
        assert response["total"] == 2
        assert len(response["sessions"]) == 2
        assert response["sessions"][0]["session_id"] == "id-1"


@pytest.mark.asyncio
async def test_list_sessions_empty(mock_session_manager):
    mock_session_manager.list_sessions.return_value = []

    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool("list_sessions", {})

        response = json.loads(result[0].text)  # type: ignore
        assert response["total"] == 0
        assert response["sessions"] == []


# ==========================================================================
# get_session_urls tool
# ==========================================================================

@pytest.mark.asyncio
async def test_list_tools_includes_get_session_urls():
    tools = await handle_list_tools()  # type: ignore
    tool_names = [t.name for t in tools]
    assert "get_session_urls" in tool_names

    tool = next(t for t in tools if t.name == "get_session_urls")
    assert "session_id" in tool.inputSchema["properties"]
    assert "as_json" in tool.inputSchema["properties"]
    assert "base_url" in tool.inputSchema["properties"]
    assert tool.inputSchema["required"] == ["session_id"]


@pytest.mark.asyncio
async def test_get_session_urls_as_json_default(mock_session_manager):
    """Default (as_json=true) returns chunks list with session_id and chunk_index."""
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool(
            "get_session_urls",
            {"session_id": "mock-session-id"},
        )

        response = json.loads(result[0].text)  # type: ignore
        assert response["success"] is True
        assert response["session_id"] == "mock-session-id"
        assert response["total_chunks"] == 5
        assert "chunks" in response
        assert "chunk_urls" not in response
        assert len(response["chunks"]) == 5
        for i, chunk in enumerate(response["chunks"]):
            assert chunk == {"session_id": "mock-session-id", "chunk_index": i}


@pytest.mark.asyncio
async def test_get_session_urls(mock_session_manager):
    """as_json=false returns URL list."""
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool(
            "get_session_urls",
            {"session_id": "mock-session-id", "base_url": TEST_WEB_BASE_URL, "as_json": False},
        )

        response = json.loads(result[0].text)  # type: ignore
        assert response["success"] is True
        assert response["session_id"] == "mock-session-id"
        assert response["total_chunks"] == 5
        assert "chunk_urls" in response
        assert "chunks" not in response
        assert len(response["chunk_urls"]) == 5
        for i, url in enumerate(response["chunk_urls"]):
            assert url == f"{TEST_WEB_BASE_URL}/sessions/mock-session-id/chunks/{i}"


@pytest.mark.asyncio
async def test_get_session_urls_default_base_url(mock_session_manager):
    """Without base_url, falls back to GOFR_DIG_WEB_URL or localhost."""
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        with patch.dict("os.environ", {"GOFR_DIG_WEB_URL": "https://proxy.example.com"}):
            result = await handle_call_tool(
                "get_session_urls",
                {"session_id": "mock-session-id", "as_json": False},
            )
            response = json.loads(result[0].text)  # type: ignore
            assert all(
                url.startswith("https://proxy.example.com/sessions/")
                for url in response["chunk_urls"]
            )


@pytest.mark.asyncio
async def test_get_session_urls_missing_session_id():
    result = await handle_call_tool("get_session_urls", {})
    response = json.loads(result[0].text)  # type: ignore
    assert response["success"] is False
    assert "INVALID_ARGUMENT" in response.get("error_code", "")


@pytest.mark.asyncio
async def test_get_session_urls_session_not_found(mock_session_manager):
    from app.exceptions import SessionNotFoundError

    mock_session_manager.get_session_info.side_effect = SessionNotFoundError(
        "SESSION_NOT_FOUND", "Session not found", {"session_id": "bad-id"}
    )
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool(
            "get_session_urls",
            {"session_id": "bad-id", "base_url": TEST_WEB_BASE_URL},
        )
        response = json.loads(result[0].text)  # type: ignore
        assert response["success"] is False


# ==========================================================================
# get_session tool
# ==========================================================================

@pytest.mark.asyncio
async def test_list_tools_includes_get_session():
    tools = await handle_list_tools()  # type: ignore
    tool_names = [t.name for t in tools]
    assert "get_session" in tool_names

    tool = next(t for t in tools if t.name == "get_session")
    assert "session_id" in tool.inputSchema["properties"]
    assert "max_bytes" in tool.inputSchema["properties"]
    assert tool.inputSchema["required"] == ["session_id"]


@pytest.mark.asyncio
async def test_get_session_joins_all_chunks(mock_session_manager):
    """get_session concatenates all chunks into a single content string."""
    mock_session_manager.get_chunk.side_effect = lambda sid, i, group=None: f"chunk{i}"
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool(
            "get_session",
            {"session_id": "mock-session-id"},
        )

        response = json.loads(result[0].text)  # type: ignore
        assert response["success"] is True
        assert response["session_id"] == "mock-session-id"
        assert response["total_chunks"] == 5
        assert response["content"] == "chunk0chunk1chunk2chunk3chunk4"
        assert response["url"] == "http://example.com"
        assert "total_size_bytes" in response


@pytest.mark.asyncio
async def test_get_session_content_too_large(mock_session_manager):
    """get_session returns error when session exceeds max_bytes."""
    mock_session_manager.get_session_info.return_value = {
        "session_id": "mock-session-id",
        "total_chunks": 5,
        "chunk_size": 1000,
        "url": "http://example.com",
        "total_size_bytes": 10_000_000,
        "created_at": "2025-01-01T00:00:00Z",
        "group": "test-group",
    }
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool(
            "get_session",
            {"session_id": "mock-session-id"},
        )

        response = json.loads(result[0].text)  # type: ignore
        assert response["success"] is False
        assert response["error_code"] == "CONTENT_TOO_LARGE"
        assert response["details"]["total_size_bytes"] == 10_000_000


@pytest.mark.asyncio
async def test_get_session_custom_max_bytes(mock_session_manager):
    """get_session respects a custom max_bytes value."""
    mock_session_manager.get_session_info.return_value = {
        "session_id": "mock-session-id",
        "total_chunks": 5,
        "chunk_size": 1000,
        "url": "http://example.com",
        "total_size_bytes": 6000,
        "created_at": "2025-01-01T00:00:00Z",
        "group": "test-group",
    }
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool(
            "get_session",
            {"session_id": "mock-session-id", "max_bytes": 3000},
        )

        response = json.loads(result[0].text)  # type: ignore
        assert response["success"] is False
        assert response["error_code"] == "CONTENT_TOO_LARGE"
        assert response["details"]["max_bytes"] == 3000


@pytest.mark.asyncio
async def test_get_session_missing_session_id():
    result = await handle_call_tool("get_session", {})
    response = json.loads(result[0].text)  # type: ignore
    assert response["success"] is False
    assert "INVALID_ARGUMENT" in response.get("error_code", "")


@pytest.mark.asyncio
async def test_get_session_not_found(mock_session_manager):
    from app.exceptions import SessionNotFoundError

    mock_session_manager.get_session_info.side_effect = SessionNotFoundError(
        "SESSION_NOT_FOUND", "Session not found", {"session_id": "bad-id"}
    )
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool(
            "get_session",
            {"session_id": "bad-id"},
        )
        response = json.loads(result[0].text)  # type: ignore
        assert response["success"] is False