# Tool Reference

A complete list of commands available in `gofr-dig`.

For how to use them together, see the **[Workflow Guide](workflow.md)**.

## Index

- [`ping`](#ping) — Health check
- [`set_antidetection`](#set_antidetection) — Configure scraping profile
- [`get_content`](#get_content) — Fetch and extract page text
- [`get_structure`](#get_structure) — Analyze page layout
- [`get_session_info`](#get_session_info) — Get session metadata
- [`get_session_chunk`](#get_session_chunk) — Retrieve one chunk
- [`list_sessions`](#list_sessions) — Browse all sessions
- [`get_session_urls`](#get_session_urls) — Get chunk references (JSON or URLs)
- [`get_session`](#get_session) — Get full session content

## Commands

### `ping`
Checks if the service is running.
*   **Returns**: "ok" if healthy.

---

### `set_antidetection`
Configures how the scraper presents itself to websites to avoid being blocked.

*   `profile` (string):
    *   `balanced` (Default): Good for most sites.
    *   `stealth`: Mimics a real user more closely.
    *   `browser_tls`: Advanced mimicry for strict sites.
*   `respect_robots_txt` (bool): Whether to follow the site's "do not crawl" rules.

---

### `get_content`
Downloads text from a URL.

*   `url` (string): The page to read.
*   `depth` (number): 
    *   `1` (Default): Read only this page.
    *   `2+`: Read this page and follow links to other pages.

**Returns**: The text content, or a `session_id` if the result is large.

---

### `get_structure`
Analyzes a page layout without downloading all text. Useful for finding specific sections to target.

*   `url` (string): The page to analyze.

---

### `get_session_info`
Gets details about a saved scraping session.

*   `session_id` (string): The ID returned by `get_content`.

---

### `get_session_chunk`
Retrieves a specific piece of a large result.

*   `session_id` (string): The session ID.
*   `chunk_index` (number): Which piece to get (starts at 0).

---

### `list_sessions`
Shows all saved sessions currently on the server.

---

### `get_session_urls`
Get references to every chunk in a session, either as a JSON list or as plain HTTP URLs.

*   `session_id` (string, **required**): The session GUID from a previous `get_content` call.
*   `as_json` (bool, default: `true`):
    *   `true`: Returns a `chunks` list of `{session_id, chunk_index}` objects — ideal for MCP-based automation (N8N, agents) that will call `get_session_chunk` next.
    *   `false`: Returns a `chunk_urls` list of plain HTTP URLs — ideal for HTTP fan-out (Make, Zapier).
*   `base_url` (string, optional): Override the web-server base URL. Only used when `as_json=false`. Auto-detected from `GOFR_DIG_WEB_URL` env if omitted.

**Returns** (as_json=true):
```json
{
  "success": true,
  "session_id": "abc-123",
  "url": "https://example.com",
  "total_chunks": 3,
  "chunks": [
    {"session_id": "abc-123", "chunk_index": 0},
    {"session_id": "abc-123", "chunk_index": 1},
    {"session_id": "abc-123", "chunk_index": 2}
  ]
}
```

**Returns** (as_json=false):
```json
{
  "success": true,
  "session_id": "abc-123",
  "url": "https://example.com",
  "total_chunks": 3,
  "chunk_urls": [
    "http://localhost:8072/sessions/abc-123/chunks/0",
    "http://localhost:8072/sessions/abc-123/chunks/1",
    "http://localhost:8072/sessions/abc-123/chunks/2"
  ]
}
```

---

### `get_session`
Retrieve and join ALL chunks of a session into a single text response.

*   `session_id` (string, **required**): The session GUID from a previous `get_content` call.
*   `max_bytes` (integer, default: `5242880` / 5 MB): Maximum allowed size in bytes for the joined content. Returns an error if the session exceeds this limit — fall back to `get_session_chunk` for large sessions.

**Returns**:
```json
{
  "success": true,
  "session_id": "abc-123",
  "url": "https://example.com",
  "total_chunks": 3,
  "total_size_bytes": 12345,
  "content": "Full concatenated text of all chunks..."
}
```

**Error** (content too large):
```json
{
  "success": false,
  "error_code": "CONTENT_TOO_LARGE",
  "message": "Session content is 8,000,000 bytes, exceeding max_bytes limit of 5,242,880.",
  "details": {"session_id": "abc-123", "total_size_bytes": 8000000, "max_bytes": 5242880, "total_chunks": 10}
}
```
