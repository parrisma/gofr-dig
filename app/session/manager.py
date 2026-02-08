import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
from gofr_common.storage import FileStorage, PermissionDeniedError
from app.exceptions import SessionNotFoundError, SessionValidationError

class SessionManager:
    def __init__(self, storage_dir: Path | str, default_chunk_size: int = 4000):
        self.storage = FileStorage(storage_dir)
        self.default_chunk_size = default_chunk_size

    def create_session(self, content: Any, url: str, group: Optional[str] = None, chunk_size: Optional[int] = None) -> str:
        """
        Create a new session from content.
        
        Args:
            content: The content to store (dict, list, or str)
            url: Source URL
            group: Owner group
            chunk_size: Optional override for chunk size
            
        Returns:
            Session ID (GUID)
        """
        # Serialize content
        if isinstance(content, str):
            text_content = content
        else:
            text_content = json.dumps(content, ensure_ascii=False)
            
        data_bytes = text_content.encode("utf-8")
        
        # Calculate chunks
        c_size = chunk_size or self.default_chunk_size
        
        total_chars = len(text_content)
        total_chunks = math.ceil(total_chars / c_size) if total_chars > 0 else 1
        
        # Save to storage
        guid = self.storage.save(
            data=data_bytes,
            format="json",
            group=group,
            url=url,
            chunk_size=c_size,
            total_chunks=total_chunks,
            total_chars=total_chars
        )
        
        return guid

    def get_session_info(self, session_id: str, group: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metadata for a session.
        
        Args:
            session_id: Session GUID
            group: Requesting group
            
        Returns:
            Dict with session info
        """
        # Access metadata directly to avoid reading blob
        # Note: We rely on FileStorage implementation details here (metadata_repo)
        # Ideally FileStorage should expose get_metadata()
        
        guid = session_id
        metadata = self.storage.metadata_repo.get(guid)
        
        if not metadata:
             # Try resolving alias
            resolved = self.storage.resolve_guid(session_id)
            if resolved:
                guid = resolved
                metadata = self.storage.metadata_repo.get(guid)
        
        if not metadata:
            raise SessionNotFoundError(
                "SESSION_NOT_FOUND",
                f"Session not found: {session_id}",
                {"session_id": session_id},
            )
            
        if group and metadata.group and metadata.group != group:
            raise PermissionDeniedError(f"Access denied to session {session_id}")
            
        return {
            "session_id": metadata.guid,
            "url": metadata.extra.get("url", ""),
            "created_at": metadata.created_at,
            "total_size_bytes": metadata.size,
            "total_chars": metadata.extra.get("total_chars", 0),
            "total_chunks": metadata.extra.get("total_chunks", 1),
            "chunk_size": metadata.extra.get("chunk_size", self.default_chunk_size),
            "group": metadata.group
        }

    def list_sessions(self, group: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all sessions, optionally filtered by group.

        Args:
            group: If provided, only return sessions owned by this group.

        Returns:
            List of session info dicts (same shape as get_session_info output).
        """
        guids = self.storage.metadata_repo.list_all(group=group)
        sessions: List[Dict[str, Any]] = []
        for guid in guids:
            metadata = self.storage.metadata_repo.get(guid)
            if metadata is None:
                continue
            sessions.append({
                "session_id": metadata.guid,
                "url": metadata.extra.get("url", ""),
                "created_at": metadata.created_at,
                "total_size_bytes": metadata.size,
                "total_chars": metadata.extra.get("total_chars", 0),
                "total_chunks": metadata.extra.get("total_chunks", 1),
                "chunk_size": metadata.extra.get("chunk_size", self.default_chunk_size),
                "group": metadata.group,
            })
        return sessions

    def get_chunk(self, session_id: str, chunk_index: int, group: Optional[str] = None) -> str:
        """
        Get a specific chunk of text content.
        
        Args:
            session_id: Session GUID
            chunk_index: 0-based index
            group: Requesting group
            
        Returns:
            Text content of the chunk
        """
        # Retrieve full data (this checks permission)
        result = self.storage.get(session_id, group=group)
        if not result:
            raise SessionNotFoundError(
                "SESSION_NOT_FOUND",
                f"Session not found: {session_id}",
                {"session_id": session_id},
            )
            
        data_bytes, fmt = result
        text_content = data_bytes.decode("utf-8")
        
        # Get metadata for chunk size
        # We can use the internal metadata since we already verified permission via get()
        # But let's use get_session_info for consistency and to get the stored chunk_size
        info = self.get_session_info(session_id, group=group)
        chunk_size = info["chunk_size"]
        total_chunks = info["total_chunks"]
        
        if chunk_index < 0 or chunk_index >= total_chunks:
            raise SessionValidationError(
                "INVALID_CHUNK_INDEX",
                f"Invalid chunk index {chunk_index}. Valid range: 0–{total_chunks - 1}",
                {"chunk_index": chunk_index, "total_chunks": total_chunks},
            )
            
        start = chunk_index * chunk_size
        end = start + chunk_size
        
        return text_content[start:end]
