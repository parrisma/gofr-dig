# Tool Reference

A complete list of commands available in `gofr-dig`.

For how to use them together, see the **[Workflow Guide](workflow.md)**.

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
Returns a list of HTTP links to download session chunks directly, useful for external automation tools.

*   `session_id` (string): The session ID.
