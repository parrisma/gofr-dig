# Tool Reference

Complete reference for every MCP tool exposed by **gofr-dig**.
Auto-generated from the live code — treat this as the authoritative source.

See **[Workflow Guide](workflow.md)** for typical usage patterns.

---

## ping

Health check. Returns `{status: "ok", service: "gofr-dig"}` when the server is reachable.
Call this first to verify connectivity before making scraping requests.

**Parameters:** none

---

## set_antidetection

Configure anti-detection settings BEFORE calling `get_content` or `get_structure`.
Settings persist for the remainder of this MCP session.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| profile | string | yes | — | One of `balanced`, `stealth`, `browser_tls`, `none`, `custom`. Start with `balanced`; escalate to `stealth` or `browser_tls` if you get FETCH_ERROR or empty content. |
| custom_headers | object | no | — | Custom HTTP headers (only with `profile=custom`). Example: `{"Accept-Language": "en-US"}` |
| custom_user_agent | string | no | — | Custom User-Agent string (only with `profile=custom`). |
| rate_limit_delay | number | no | 1.0 | Seconds between requests (range 0–60). Increase if you see rate-limit errors. |
| max_response_chars | integer | no | 400000 | Max response size in characters (range 4000–4000000). |
| auth_token | string | no | — | JWT token for authentication. |

**Returns:** `{success, profile, rate_limit_delay, max_response_chars}`

**Errors:** INVALID_PROFILE, INVALID_RATE_LIMIT, INVALID_MAX_RESPONSE_CHARS

---

## get_content

Fetch a web page and extract its readable text. This is the primary scraping tool.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| url | string | yes | — | Full URL to fetch (must start with `http://` or `https://`). |
| depth | integer | no | 1 | Crawl depth (1–3). 1 = single page. 2 = page + linked pages. 3 = two levels of links. |
| max_pages_per_level | integer | no | 5 | Max pages fetched per depth level (1–20). |
| selector | string | no | — | CSS selector to extract only matching elements (e.g. `#main-content`, `article`). |
| include_links | boolean | no | true | Include extracted hyperlinks in the result. |
| include_images | boolean | no | false | Include image URLs and alt text. |
| include_meta | boolean | no | true | Include page metadata (description, keywords, Open Graph). |
| session | boolean | no | false | `true` = store server-side, return `session_id`. `false` = inline. |
| filter_noise | boolean | no | true | Strip ad/cookie-banner noise from extracted text. |
| chunk_size | integer | no | 4000 | Session chunk size in characters. Only used with `session=true`. |
| max_bytes | integer | no | 5242880 | Max inline response size in bytes (5 MB). |
| timeout_seconds | number | no | 60 | Per-request fetch timeout in seconds. |
| parse_results | boolean | no | true | Run the deterministic news parser on crawl results. Returns structured stories with dedup, classification, and quality signals. Applies to all depths. |
| source_profile_name | string | no | — | Source profile for the parser (e.g. `scmp`). Controls site-specific date patterns, section labels, and noise markers. Only used when `parse_results=true`. |
| auth_token | string | no | — | JWT token for authentication. |

### Depth Behaviour

- **depth=1** — scrape a single page.
- **depth=2** — scrape the page AND the pages it links to.
- **depth=3** — three levels deep (slow, use sparingly).

### Session Mode

- `session=true` — store results server-side, return a `session_id`. Retrieve later with `get_session`, `get_session_chunk`, or `get_session_urls`.
- `session=false` (default) — return all content inline.

### Parse Mode

- `parse_results=true` (default) — crawl results are processed by the deterministic news parser. Returns `{feed_meta, stories}` with deduplicated articles, section labels, date extraction, and parse-quality signals. Applies to all depths.
- `parse_results=false` — returns raw crawl output (pages, text, links, etc.).
- Use `source_profile_name` (e.g. `scmp`) for site-specific parsing rules. Omit for the generic fallback profile.

### Tips

- Call `get_structure` first to find a good CSS selector, then pass it as `selector`.
- Use `include_links=false` and `include_meta=false` if you only need text.
- If you get ROBOTS_BLOCKED, choose a URL/path allowed by `robots.txt`.
- If you get FETCH_ERROR, try `set_antidetection` with `profile=stealth` or `browser_tls`.

**Errors:** INVALID_URL, FETCH_ERROR, ROBOTS_BLOCKED, EXTRACTION_ERROR, MAX_DEPTH_EXCEEDED, MAX_PAGES_EXCEEDED, PARSE_ERROR, CONTENT_TOO_LARGE

---

## get_structure

Analyze a web page's structure WITHOUT extracting full text.
Use this BEFORE `get_content` to discover the page layout and find CSS selectors.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| url | string | yes | — | Full URL to analyze (must include `http://` or `https://`). |
| selector | string | no | — | CSS selector to scope the analysis to a specific part of the page. |
| include_navigation | boolean | no | true | Include navigation menus and their links. |
| include_internal_links | boolean | no | true | Include links to same domain. |
| include_external_links | boolean | no | true | Include links to other domains. |
| include_forms | boolean | no | true | Include HTML forms with their fields and actions. |
| include_outline | boolean | no | true | Include heading hierarchy (h1–h6) as an outline. |
| timeout_seconds | number | no | 60 | Per-request fetch timeout in seconds. |
| auth_token | string | no | — | JWT token for authentication. |

**Returns:** `{success, url, title, language, sections, navigation, internal_links, external_links, forms, outline}`

**Errors:** INVALID_URL, FETCH_ERROR, ROBOTS_BLOCKED, EXTRACTION_ERROR

---

## get_session_info

Get metadata for a stored scraping session.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| session_id | string | yes | — | Session GUID returned by `get_content` when `session=true`. |
| auth_token | string | no | — | JWT token for authentication. |

**Returns:** `{success, session_id, url, total_chunks, total_size, created_at}`

**Errors:** SESSION_NOT_FOUND

---

## get_session_chunk

Retrieve one chunk of text from a stored session.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| session_id | string | yes | — | Session GUID from a previous `get_content` call. |
| chunk_index | integer | yes | — | Zero-based chunk index (0 to `total_chunks-1`). |
| auth_token | string | no | — | JWT token for authentication. |

**Returns:** `{success, session_id, chunk_index, total_chunks, content}`

**Tip:** Prefer `get_session` if you need all chunks at once and the total size is under 5 MB.

**Errors:** SESSION_NOT_FOUND, CHUNK_NOT_FOUND

---

## list_sessions

List all stored scraping sessions. Returns an empty list when no sessions exist.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| auth_token | string | no | — | JWT token for authentication. |

**Returns:** `{success, sessions: [{session_id, url, total_chunks, total_size, created_at}], total}`

---

## get_session_urls

Get references to every chunk in a session.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| session_id | string | yes | — | Session GUID from a previous `get_content` call. |
| as_json | boolean | no | true | `true` = list of `{session_id, chunk_index}` objects. `false` = list of plain HTTP URLs. |
| base_url | string | no | — | Override the web-server base URL (e.g. `http://myhost:PORT`). Only used when `as_json=false`. |
| auth_token | string | no | — | JWT token for authentication. |

**Returns (as_json=true):** `{success, session_id, url, total_chunks, chunks: [{session_id, chunk_index}, ...]}`

**Returns (as_json=false):** `{success, session_id, url, total_chunks, chunk_urls: [url, ...]}`

**Errors:** SESSION_NOT_FOUND

---

## get_session

Retrieve and join ALL chunks of a session into a single text response.
Preferred over iterating `get_session_chunk` when you need the full content.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| session_id | string | yes | — | Session GUID from a previous `get_content` call. |
| max_bytes | integer | no | 5242880 | Max allowed size in bytes. Returns error if session exceeds limit. |
| timeout_seconds | number | no | 60 | Timeout in seconds for retrieval. |
| auth_token | string | no | — | JWT token for authentication. |

**Returns:** `{success, session_id, url, total_chunks, total_size, content}`

**Errors:** SESSION_NOT_FOUND, CONTENT_TOO_LARGE

---

## Error Codes

Every error response includes `{success: false, error_code, error, recovery_strategy}`.
The `recovery_strategy` field provides actionable guidance.

| Error Code | Recovery Strategy |
|------------|-------------------|
| INVALID_URL | Ensure the URL is properly formatted with `http://` or `https://` scheme. |
| URL_NOT_FOUND | Verify the URL exists and is accessible. The server returned 404. |
| FETCH_ERROR | Check network connectivity and that the target site is online. Try again later. |
| TIMEOUT_ERROR | The request timed out. Try increasing timeout or check if the site is slow/unresponsive. |
| CONNECTION_ERROR | Could not connect to the server. Verify the URL and check network connectivity. |
| ROBOTS_BLOCKED | Access blocked by `robots.txt`. Choose a URL/path allowed by the target site's robots policy. |
| ACCESS_DENIED | The server denied access. Try a different anti-detection profile or custom headers. |
| RATE_LIMITED | Too many requests. Increase `rate_limit_delay` in `set_antidetection`. |
| RATE_LIMIT_EXCEEDED | Inbound rate limit exceeded. Wait and retry after the reset window. |
| SSRF_BLOCKED | The URL resolves to a private/internal IP. Requests to internal networks are blocked. |
| SELECTOR_NOT_FOUND | The CSS selector matched no elements. Verify the selector syntax and that the element exists. |
| INVALID_SELECTOR | The CSS selector syntax is invalid. Check for typos. |
| EXTRACTION_ERROR | Failed to extract content. The page may have unexpected structure or encoding. |
| ENCODING_ERROR | Character encoding issue. The page may use an unsupported encoding. |
| INVALID_PROFILE | Use one of: `stealth`, `balanced`, `none`, `custom`, `browser_tls`. |
| INVALID_HEADERS | Custom headers must be a dictionary with string keys and values. |
| INVALID_RATE_LIMIT | `rate_limit_delay` must be a non-negative number (seconds between requests). |
| INVALID_MAX_RESPONSE_CHARS | `max_response_chars` must be between 4000 and 4000000. Default is 400000. |
| MAX_DEPTH_EXCEEDED | Crawl depth is limited to 3. Use depth 1, 2, or 3. |
| MAX_PAGES_EXCEEDED | Too many pages requested. Reduce `max_pages_per_level` (max 20). |
| CONTENT_TOO_LARGE | Response exceeds `max_bytes`. Use `session=true` or increase `max_bytes`. |
| AUTH_ERROR | Provide a valid JWT token in `auth_token`. |
| PERMISSION_DENIED | Your token's groups do not include the group that owns this session. |
| SESSION_ERROR | Session operation failed. Use `list_sessions` to check available sessions. |
| SESSION_NOT_FOUND | Session ID not found. Use `list_sessions` to discover sessions, or create one with `get_content(session=true)`. |
| INVALID_CHUNK_INDEX | Chunk index out of range. Use `get_session_info` to check the total number of chunks. |
| INVALID_ARGUMENT | A required argument is missing or invalid. Check the tool schema. |
| PARSE_ERROR | The news parser failed. Retry with `parse_results=false` for raw output, or check `source_profile_name`. |
| CONFIGURATION_ERROR | Check server configuration. Contact administrator if issue persists. |
| UNKNOWN_TOOL | Use one of the tools listed in this reference. |
