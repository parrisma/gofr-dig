import pytest
import json
from unittest.mock import MagicMock, patch
from app.mcp_server.mcp_server import handle_call_tool, handle_list_tools
from app.session.manager import SessionManager
from app.scraping.fetcher import FetchResult

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
                    {"url": "http://example.com", "session": True}
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
        
        mock_session_manager.get_session_info.assert_called_with("mock-session-id")
        response = json.loads(result[0].text)  # type: ignore
        assert response["total_chunks"] == 5

@pytest.mark.asyncio
async def test_get_session_chunk(mock_session_manager):
    with patch("app.mcp_server.mcp_server.session_manager", mock_session_manager):
        result = await handle_call_tool(
            "get_session_chunk",
            {"session_id": "mock-session-id", "chunk_index": 0}
        )
        
        mock_session_manager.get_chunk.assert_called_with("mock-session-id", 0)
        response = json.loads(result[0].text)  # type: ignore
        assert response == "Mock chunk content"
