# Proposal: Session Management for Large Datasets in GOFR-DIG

## 1. Problem Statement

`gofr-dig` currently returns scraped content directly in the MCP tool response. For large websites or deep crawls, this data can easily exceed the context window limits of LLMs (e.g., 128k tokens). Returning huge JSON payloads directly to the prompt is inefficient and often causes truncation or errors.

## 2. Proposed Solution

Implement a **Session Management** pattern similar to `gofr-plot`'s Proxy Mode. Instead of returning the full dataset, the MCP tool will:
1.  Store the scraped result locally on the server.
2.  Return a lightweight **Session ID (GUID)** and a summary of the data.
3.  Provide mechanisms to retrieve the data in manageable **chunks** or stream it via a **URL**.

This approach allows the LLM to "peek" at the data or request specific parts, rather than being overwhelmed by the entire dataset at once.

## 3. Architecture

### 3.1. Storage Layer
We will use the shared storage module from `gofr-common` (`gofr_common.storage.FileStorage`). This module provides a generic blob storage implementation with metadata separation and group-based access control, originally derived from `gofr-plot` but generalized for any data type.

*   **Blob Storage**: Stores the raw scraped content (JSON) on disk using `FileBlobRepository`.
*   **Metadata Storage**: Stores session details (GUID, timestamp, source URL, size, group ownership) using `JsonMetadataRepository`.
*   **Directory Structure**:
    ```
    data/
      sessions/
        metadata.json       # Index of all sessions
        {guid}.json         # Raw scraped data
    ```

### 3.2. Session Manager
A new `SessionManager` class will handle:
*   Creating new sessions from scrape results.
*   Chunking logic (splitting large text/JSON into smaller segments).
*   Retrieving session metadata and chunks.
*   Housekeeping (expiring old sessions).

### 3.3. Access Control
We will leverage the existing JWT authentication and Group model (from `gofr-common`):
*   Sessions are owned by the **Group** that created them.
*   Only tokens with the matching Group can access the session data.

## 4. Implementation Details

### 4.1. New MCP Tool Parameters
Existing tools (`get_content`, `get_structure`, `crawl`) will accept a new optional parameter:

*   `session` (boolean, default: `false`): If `true`, the tool saves the result and returns a Session ID instead of the full content.
*   `chunk_size` (integer, optional): Desired size of chunks (in characters or tokens) for subsequent retrieval.

**Example Response (Session Mode):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "summary": {
    "url": "https://example.com",
    "total_size_bytes": 154000,
    "total_chunks": 15,
    "chunk_size": 10000
  },
  "preview": "Title: Example Domain\n..."
}
```

### 4.2. New MCP Tools

#### `get_session_info`
Retrieves metadata about a session.
*   **Input**: `session_id`
*   **Output**: Size, chunk count, creation time, source URL.

#### `get_session_chunk`
Retrieves a specific chunk of data from a session.
*   **Input**: `session_id`, `chunk_index` (0-based)
*   **Output**: The text content of that chunk.

### 4.3. Web Server Endpoints
Add endpoints to `GofrDigWebServer` to allow direct download or streaming.

*   `GET /session/{session_id}`: Download the full JSON result.
*   `GET /session/{session_id}/stream`: Stream the content (useful for very large datasets).
*   **Auth**: Requires `Authorization: Bearer <token>` header.

## 5. Workflow Example

1.  **User**: "Scrape https://news.site/archive and give me a summary. It's a huge page."
2.  **Agent**: Calls `get_content(url="...", session=true)`.
3.  **GOFR-DIG**: Scrapes data, saves to `data/sessions/blobs/{guid}.json`, returns GUID `abc-123`.
4.  **Agent**: Receives GUID. Calls `get_session_info(session_id="abc-123")` to see it has 50 chunks.
5.  **Agent**: Calls `get_session_chunk(session_id="abc-123", chunk_index=0)` to read the first chunk (header/intro).
6.  **Agent**: Processes chunk 0. Decides it needs more detail on a specific topic found in the middle.
7.  **Agent**: Calls `get_session_chunk(session_id="abc-123", chunk_index=25)`.
8.  **Agent**: Summarizes findings to the user.

## 6. Roadmap

1.  **Phase 1: Storage & Core Logic**
    *   Implement `SessionStorage` (adapted from `gofr-plot`).
    *   Implement `SessionManager` with chunking logic.

2.  **Phase 2: Web API**
    *   Add `/session/{id}` endpoints to `main_web.py`.
    *   Integrate JWT auth checks.

3.  **Phase 3: MCP Integration**
    *   Update `get_content` / `get_structure` to support `session=true`.
    *   Add `get_session_info` and `get_session_chunk` tools.

4.  **Phase 4: Documentation & Testing**
    *   Update README.
    *   Add unit tests for chunking and storage.
