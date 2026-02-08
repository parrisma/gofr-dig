# Workflow Guide

Step-by-step usage of gofr-dig's MCP tools. For full parameter details see [TOOLS.md](TOOLS.md).

## Recommended Sequence

```
1. set_antidetection   ← configure (optional — sensible defaults apply)
2. get_structure       ← discover page layout and selectors
3. get_content         ← extract text (depth > 1 auto-creates a session)
4. get_session_chunk   ← iterate chunks if a session_id was returned
5. list_sessions       ← browse previous sessions
6. get_session_urls    ← get HTTP URLs for automation fan-out
```

---

## 1. Configure Anti-Detection (optional)

Call `set_antidetection` **before** any scraping if you need something other than the defaults (balanced profile, robots.txt honoured, 1 s rate limit).

```json
{"profile": "balanced"}
```

Escalation path when a site blocks you:

| Situation | Action |
|---|---|
| Standard site | `"balanced"` (default) |
| Bot detection | `"stealth"` |
| TLS fingerprinting (Wikipedia, Cloudflare) | `"browser_tls"` |
| Blocked by robots.txt | Add `"respect_robots_txt": false` |
| Rate limited | Increase `"rate_limit_delay": 3.0` |

---

## 2. Discover Page Structure

Call `get_structure` to see sections, navigation, forms, and heading outline — without fetching all text. Use the results to pick a CSS selector for targeted extraction.

```json
{"url": "https://docs.example.com"}
```

The response includes `sections`, `outline`, `internal_links`, `navigation`, and `forms`. Look for an `id` or `class` in `sections` to use as a selector.

---

## 3. Extract Content

### Single page (depth = 1)

Returns content inline:

```json
{"url": "https://example.com/article", "selector": "#main-content"}
```

Response: `{success, url, title, text, links, headings, meta, ...}`

### Multi-page crawl (depth > 1)

Automatically stores results as a session:

```json
{"url": "https://docs.example.com", "depth": 2, "max_pages_per_level": 5}
```

Response: `{success, session_id, url, total_chunks, total_size, crawl_depth, total_pages}`

### Force session on a single page

```json
{"url": "https://example.com/very-long-page", "session": true}
```

---

## 4. Retrieve Session Content

When `get_content` returns a `session_id`, retrieve the text chunk by chunk.

### Check session metadata

```json
// get_session_info
{"session_id": "<guid>"}
```

Response: `{session_id, url, total_chunks, total_size, created_at}`

### Iterate chunks

Call `get_session_chunk` for each chunk index from **0** to **total_chunks − 1**:

```json
{"session_id": "<guid>", "chunk_index": 0}
{"session_id": "<guid>", "chunk_index": 1}
...
```

Each response: `{session_id, chunk_index, total_chunks, content}`

---

## 5. Browse Sessions

Call `list_sessions` (no parameters) to see all stored sessions with their IDs, source URLs, and sizes.

---

## 6. Automation Fan-Out

For N8N, Make, Zapier, or any HTTP-based pipeline:

```json
// get_session_urls
{"session_id": "<guid>"}
```

Response includes `chunk_urls` — an array of plain HTTP GET URLs:

```json
{
  "chunk_urls": [
    "http://localhost:8072/sessions/<guid>/chunks/0",
    "http://localhost:8072/sessions/<guid>/chunks/1",
    ...
  ]
}
```

Each URL returns one chunk's text over REST with no MCP required.

**N8N example:**

```
HTTP Request (MCP: get_content, depth=2)
  → get_session_urls(session_id)
  → Split In Batches (chunk_urls)
    → HTTP Request GET (each URL)
    → Merge text
```

---

## Error Handling

All tools return a standard error shape on failure:

```json
{
  "success": false,
  "error_code": "ROBOTS_BLOCKED",
  "message": "Disallowed by robots.txt",
  "details": {"url": "..."},
  "recovery_strategy": "Use set_antidetection with respect_robots_txt=false"
}
```

Common recovery paths:

| Error | Fix |
|---|---|
| `ROBOTS_BLOCKED` | `set_antidetection(respect_robots_txt=false)` |
| `FETCH_ERROR` | Try `profile="stealth"` or `"browser_tls"` |
| `INVALID_URL` | Ensure the URL starts with `http://` or `https://` |
| `EXTRACTION_ERROR` | Try a different CSS selector or check the page manually |
