import pytest
from app.session.manager import SessionManager
from app.exceptions import SessionNotFoundError, SessionValidationError
from gofr_common.storage import PermissionDeniedError

@pytest.fixture
def temp_storage_dir(tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    return storage_dir

@pytest.fixture
def session_manager(temp_storage_dir):
    # Initialize with a small chunk size for testing
    return SessionManager(storage_dir=temp_storage_dir, default_chunk_size=100)

def test_create_session(session_manager):
    content = {"title": "Test", "body": "This is a test content."}
    session_id = session_manager.create_session(
        content=content,
        url="http://example.com",
        group="test-group"
    )
    assert session_id is not None
    assert isinstance(session_id, str)

def test_get_session_info(session_manager):
    content = {"title": "Test", "body": "This is a test content."}
    session_id = session_manager.create_session(
        content=content,
        url="http://example.com",
        group="test-group"
    )
    
    info = session_manager.get_session_info(session_id, group="test-group")
    assert info["url"] == "http://example.com"
    assert info["total_chunks"] >= 1
    assert info["total_size_bytes"] > 0

def test_get_chunk(session_manager):
    # Create content large enough to be chunked (chunk size is 100)
    # We'll use a simple string content for predictable chunking
    long_text = "A" * 250
    content = long_text
    
    session_id = session_manager.create_session(
        content=content,
        url="http://example.com",
        group="test-group"
    )
    
    # Should have 3 chunks (100, 100, 50)
    info = session_manager.get_session_info(session_id, group="test-group")
    assert info["total_chunks"] == 3
    
    chunk0 = session_manager.get_chunk(session_id, 0, group="test-group")
    assert len(chunk0) == 100
    
    chunk2 = session_manager.get_chunk(session_id, 2, group="test-group")
    assert len(chunk2) == 50

def test_access_control(session_manager):
    content = {"text": "Secret"}
    session_id = session_manager.create_session(
        content=content,
        url="http://example.com",
        group="group-a"
    )
    
    # Should fail with wrong group
    with pytest.raises(PermissionDeniedError):
        session_manager.get_session_info(session_id, group="group-b")
        
    with pytest.raises(PermissionDeniedError):
        session_manager.get_chunk(session_id, 0, group="group-b")

def test_session_not_found(session_manager):
    with pytest.raises(SessionNotFoundError, match="Session not found"):
        session_manager.get_session_info("non-existent-id", group="test-group")

def test_invalid_chunk_index(session_manager):
    content = {"text": "Short"}
    session_id = session_manager.create_session(
        content=content,
        url="http://example.com",
        group="test-group"
    )
    
    with pytest.raises(SessionValidationError, match="Invalid chunk index"):
        session_manager.get_chunk(session_id, 99, group="test-group")


def test_list_sessions_empty(session_manager):
    sessions = session_manager.list_sessions()
    assert sessions == []


def test_list_sessions_returns_all(session_manager):
    session_manager.create_session(content="Page 1", url="http://a.com", group="grp")
    session_manager.create_session(content="Page 2", url="http://b.com", group="grp")
    session_manager.create_session(content="Page 3", url="http://c.com", group="other")

    sessions = session_manager.list_sessions()
    assert len(sessions) == 3
    urls = {s["url"] for s in sessions}
    assert urls == {"http://a.com", "http://b.com", "http://c.com"}


def test_list_sessions_filtered_by_group(session_manager):
    session_manager.create_session(content="Page 1", url="http://a.com", group="alpha")
    session_manager.create_session(content="Page 2", url="http://b.com", group="beta")
    session_manager.create_session(content="Page 3", url="http://c.com", group="alpha")

    alpha_sessions = session_manager.list_sessions(group="alpha")
    assert len(alpha_sessions) == 2
    assert all(s["group"] == "alpha" for s in alpha_sessions)

    beta_sessions = session_manager.list_sessions(group="beta")
    assert len(beta_sessions) == 1
    assert beta_sessions[0]["url"] == "http://b.com"


def test_list_sessions_has_expected_fields(session_manager):
    session_manager.create_session(content="Hello", url="http://x.com", group="g")

    sessions = session_manager.list_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert "session_id" in s
    assert "url" in s
    assert "created_at" in s
    assert "total_size_bytes" in s
    assert "total_chunks" in s
    assert "chunk_size" in s
    assert "group" in s
