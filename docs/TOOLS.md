# MCP Tools Reference

Complete parameter reference for all gofr-dig MCP tools. For step-by-step usage see [WORKFLOW.md](WORKFLOW.md); for technical internals see [ARCHITECTURE.md](ARCHITECTURE.md).

## Overview

GOFR-DIG is a web scraping and page-structure analysis service exposed via MCP. It can:

- Fetch and extract readable text from a page (with optional crawling depth)
- Analyze page structure to discover sections, navigation, and forms
- Apply anti-detection settings (headers, rate limits, robots.txt)
- Store large results in server-side sessions and retrieve them in chunks

## Tools

| Tool | Purpose |
|------|---------|
| [ping](#ping) | Health check |
| [set_antidetection](#set_antidetection) | Configure scraping behavior |
| [get_content](#get_content) | Fetch and extract page text |
| [get_structure](#get_structure) | Analyze page layout |
| [get_session_info](#get_session_info) | Get session metadata |
| [get_session_chunk](#get_session_chunk) | Retrieve session chunk |
| [list_sessions](#list_sessions) | List all stored sessions |
| [get_session_urls](#get_session_urls) | Get chunk URLs for automation |

---

## ping

Health check — verifies the MCP server is running.

**Parameters:** None

**Returns:**

```json
{"status": "ok", "service": "gofr-dig"}
```

---

## set_antidetection

Configure anti-detection settings before scraping. Call this **before** `get_content` or `get_structure`. Settings persist for the session.

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| profile | string | **Yes** | — | `stealth`, `balanced`, `none`, `custom`, or `browser_tls` |
| custom_headers | object | No | {} | Custom headers (only with profile `custom`) |
| custom_user_agent | string | No | null | Custom User-Agent (only with profile `custom`) |
| respect_robots_txt | bool | No | true | Honor robots.txt rules |
| rate_limit_delay | float | No | 1.0 | Seconds between requests (0–60) |
| max_tokens | int | No | 100000 | Max tokens in responses (1000–1000000). ~4 chars per token. |

### Profiles

| Profile | Description | Best For |
|---|---|---|
| `stealth` | Full browser headers, rotating UA | Sites with strict bot detection |
| `balanced` | Standard browser headers, fixed UA | Most websites (recommended) |
| `none` | Minimal headers | APIs or permissive sites |
| `custom` | User-defined headers and UA | Special requirements |
| `browser_tls` | Chrome TLS fingerprint via curl_cffi | Sites using TLS fingerprinting (e.g., Wikipedia) |

### Returns

```json
{
  "success": true,
  "profile": "balanced",
  "respect_robots_txt": true,
  "rate_limit_delay": 1.0,
  "max_tokens": 100000
}
```

### Error Codes

- `INVALID_PROFILE` — Unknown profile name
- `INVALID_RATE_LIMIT` — Value outside 0–60
- `INVALID_MAX_TOKENS` — Value outside 1000–1000000

### Examples

```json
// Stealth with slow rate
{"profile": "stealth", "rate_limit_delay": 2.0}

// Bypass robots.txt
{"profile": "balanced", "respect_robots_txt": false}

// TLS fingerprinting for Wikipedia
{"profile": "browser_tls"}

// Limit response size
{"profile": "balanced", "max_tokens": 50000}
```

---

## get_content

Fetch a web page and extract its text content. Supports recursive crawling up to depth 3 and server-side session storage for large results.

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| url | string | **Yes** | — | URL to fetch (http/https) |
| depth | int | No | 1 | Crawl depth: 1=single page, 2–3=follow links |
| max_pages_per_level | int | No | 5 | Max pages per depth level (1–20) |
| selector | string | No | null | CSS selector to extract specific content (e.g., `#main`, `article`) |
| include_links | bool | No | true | Include extracted links |
| include_images | bool | No | false | Include image URLs and alt text |
| include_meta | bool | No | true | Include page metadata (description, keywords, og:tags) |
| session | bool | No | false | Save to a session, return `session_id` instead of full content. **Auto-enabled when depth > 1.** |
| chunk_size | int | No | 4000 | Chunk size in characters (only used when `session=true`) |

### Returns (depth=1)

```json
{
  "success": true,
  "url": "https://example.com",
  "title": "Example Domain",
  "text": "This domain is for use in illustrative examples...",
  "language": "en",
  "links": [{"href": "https://www.iana.org/domains/example", "text": "More information..."}],
  "headings": [{"level": 1, "text": "Example Domain"}],
  "images": [],
  "meta": {"description": "Example Domain", "keywords": null}
}
```

### Returns (depth > 1)

> **Note:** `depth > 1` automatically enables session mode. The response always uses the session format below, even if `session` was not explicitly set.

```json
{
  "success": true,
  "session_id": "<guid>",
  "total_chunks": 12,
  "total_size": 48000,
  "message": "Content stored in session. Use get_session_chunk to retrieve."
}
```

### Returns (session=true)

```json
{
  "success": true,
  "session_id": "<guid>",
  "total_chunks": 12,
  "total_size": 48000,
  "message": "Content stored in session. Use get_session_chunk to retrieve."
}
```

### Error Codes

- `INVALID_URL` — Malformed or unsupported scheme
- `FETCH_ERROR` — Network error or timeout
- `ROBOTS_BLOCKED` — Denied by robots.txt
- `EXTRACTION_ERROR` — Failed to parse page content
- `MAX_DEPTH_EXCEEDED` — Depth limited to 3
- `MAX_PAGES_EXCEEDED` — Reduce `max_pages_per_level` (max 20)

### Examples

```json
// Single page
{"url": "https://example.com/article"}

// Extract specific section
{"url": "https://example.com", "selector": "#main-content"}

// Crawl docs site
{"url": "https://docs.example.com", "depth": 2, "max_pages_per_level": 5}

// Large content → session mode
{"url": "https://example.com", "depth": 2, "session": true, "chunk_size": 4000}
```

---

## get_structure

Analyze page structure without extracting full text. Use to discover selectors and layout before scraping with `get_content`.

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| url | string | **Yes** | — | URL to analyze (http/https) |
| include_navigation | bool | No | true | Include nav menus and their links |
| include_internal_links | bool | No | true | Include same-domain links |
| include_external_links | bool | No | true | Include cross-domain links |
| include_forms | bool | No | true | Include form fields and actions |
| include_outline | bool | No | true | Include heading hierarchy (h1–h6) |

### Returns

```json
{
  "success": true,
  "url": "https://example.com",
  "title": "Example Domain",
  "language": "en",
  "sections": [
    {"tag": "main", "id": "content", "classes": ["page-content"], "children": 12}
  ],
  "navigation": [
    {"type": "nav", "id": "main-nav", "links": [{"text": "Home", "href": "/"}]}
  ],
  "internal_links": [{"text": "Contact", "href": "/contact"}],
  "external_links": [{"text": "GitHub", "href": "https://github.com/example"}],
  "forms": [
    {"id": "search-form", "action": "/search", "method": "GET",
     "inputs": [{"name": "q", "type": "text", "required": true}]}
  ],
  "outline": [
    {"level": 1, "text": "Welcome"},
    {"level": 2, "text": "Features"}
  ]
}
```

### Error Codes

- `INVALID_URL` — Malformed or unsupported scheme
- `FETCH_ERROR` — Network error or timeout
- `ROBOTS_BLOCKED` — Denied by robots.txt
- `EXTRACTION_ERROR` — Failed to parse page structure

---

## get_session_info

Get metadata for a stored scraping session.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| session_id | string | **Yes** | Session GUID returned by `get_content(session=true)` |

### Returns

```json
{
  "success": true,
  "session_id": "<guid>",
  "url": "https://example.com",
  "total_chunks": 12,
  "total_size": 48000,
  "created_at": "2026-02-08T12:00:00Z"
}
```

---

## get_session_chunk

Retrieve a specific chunk of text from a session.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| session_id | string | **Yes** | Session GUID |
| chunk_index | int | **Yes** | Zero-based chunk index |

### Returns

```json
{
  "success": true,
  "session_id": "<guid>",
  "chunk_index": 0,
  "total_chunks": 12,
  "content": "..."
}
```

---

## list_sessions

List all stored scraping sessions. Use to discover available sessions before calling `get_session_info` or `get_session_chunk`.

### Parameters

None.

### Returns

```json
{
  "success": true,
  "sessions": [
    {
      "session_id": "<guid>",
      "url": "https://example.com",
      "total_chunks": 12,
      "total_size": 48000,
      "created_at": "2026-02-08T12:00:00Z"
    }
  ],
  "total": 1
}
```

---

## get_session_urls

Get a list of ready-to-GET HTTP URLs for every chunk in a session. Designed for automation services (N8N, Make, Zapier) that need to iterate chunks over plain HTTP without MCP.

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| session_id | string | **Yes** | — | Session GUID returned by `get_content(session=true)` |
| base_url | string | No | auto-detected | Override the web server base URL (e.g. `http://host:8072`) |

**Base URL resolution order:** `base_url` param → `GOFR_DIG_WEB_URL` env var → `http://localhost:{GOFR_DIG_WEB_PORT}`

### Returns

```json
{
  "success": true,
  "session_id": "<guid>",
  "url": "https://example.com",
  "total_chunks": 4,
  "chunk_urls": [
    "http://localhost:8072/sessions/<guid>/chunks/0",
    "http://localhost:8072/sessions/<guid>/chunks/1",
    "http://localhost:8072/sessions/<guid>/chunks/2",
    "http://localhost:8072/sessions/<guid>/chunks/3"
  ]
}
```

### Web Endpoint

Also available as a REST endpoint: `GET /sessions/{session_id}/urls[?base_url=...]`

### N8N Example

```
HTTP Request (MCP: get_content, session=true, depth=2)
  → get_session_urls(session_id)
  → Split In Batches (chunk_urls array)
    → HTTP Request GET (each chunk_url)
    → Merge/Aggregate text
```

---

## Standard Error Format

All tools return a consistent error shape:

```json
{
  "success": false,
  "error_code": "ERROR_CODE",
  "message": "Human-readable message",
  "details": {"context": "..."},
  "recovery_strategy": "Suggested fix"
}
```

| Error Code | Recovery |
|---|---|
| `INVALID_URL` | Include scheme (http/https) |
| `FETCH_ERROR` | Check network, retry later |
| `ROBOTS_BLOCKED` | Use `set_antidetection` with `respect_robots_txt: false` |
| `EXTRACTION_ERROR` | Try different selector or check page structure |
| `INVALID_PROFILE` | Use: stealth, balanced, none, custom, browser_tls |
| `UNKNOWN_TOOL` | Check tool name against the list above |

---

## Recommended Workflow

See [WORKFLOW.md](WORKFLOW.md) for a full step-by-step guide.

1. `set_antidetection` — configure profile and rate limits
2. `get_structure` — discover page layout and find CSS selectors
3. `get_content` — extract text (depth > 1 auto-creates a session)
4. `get_session_chunk` — iterate chunks from 0 to total_chunks-1
5. `get_session_urls` — get HTTP URLs for automation fan-out
6. `list_sessions` — browse all stored sessions
