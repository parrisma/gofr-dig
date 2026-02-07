# GOFR-DIG MCP Integration Guide (for UI/LLM)

This section explains what GOFR-DIG is, how to call its MCP tools, and how to design a UI that exposes all features for testing before integrating into automated workflows (e.g., n8n).

## What is GOFR-DIG?

GOFR-DIG is a web scraping and page-structure analysis service exposed via MCP tools. It can:

- Fetch and extract readable text from a page (with optional crawling depth).
- Analyze page structure to discover sections, navigation, and forms.
- Apply anti-detection settings (headers, rate limits, robots.txt behavior).
- Store large results in server-side sessions and retrieve them in chunks.

The MCP surface is intentionally small and consistent, so an LLM-driven UI can present a single “scrape session” workflow with controls for each step.

## MCP Tools (Overview)

All MCP calls are tool invocations with a JSON `args` object. The main tools are:

- `ping`
- `hello_world`
- `set_antidetection`
- `get_structure`
- `get_content`
- `get_session_info`
- `get_session_chunk`

## Standard Response Shapes

### Success (general)

Most tools return a JSON object with `success: true` and tool-specific fields.

### Error (standardized)

```json
{
  "success": false,
  "error_code": "ERROR_CODE",
  "message": "Human-readable message",
  "details": {"context": "..."},
  "recovery_strategy": "Suggested recovery steps"
}
```

The UI should always surface `error_code`, `message`, and `recovery_strategy` together.

## Tool Details and UI Mapping

### 1) `ping`

**Purpose:** Health check for MCP connectivity.

**Args:** `{}`

**UI:** “Test Connection” button.

### 2) `hello_world`

**Purpose:** Basic tool invocation test.

**Args:** `{ "name": "World" }`

**UI:** “Hello World” test input for debugging.

### 3) `set_antidetection`

**Purpose:** Configure scraping behavior for the session. This should be called **before** `get_content` or `get_structure`.

**Args:**

```json
{
  "profile": "balanced",
  "custom_headers": {"Accept-Language": "en-US"},
  "custom_user_agent": "...",
  "respect_robots_txt": true,
  "rate_limit_delay": 1.0,
  "max_tokens": 100000
}
```

**Profiles:** `stealth`, `balanced`, `none`, `custom`, `browser_tls`

**UI Controls:**

- Profile dropdown with short descriptions
- Robots.txt toggle
- Rate limit slider (0–60s)
- Max tokens input (1000–1,000,000)
- Custom headers + custom UA when profile=`custom`

### 4) `get_structure`

**Purpose:** Analyze page structure without full text extraction.

**Args:**

```json
{
  "url": "https://example.com",
  "include_navigation": true,
  "include_internal_links": true,
  "include_external_links": true,
  "include_forms": true,
  "include_outline": true
}
```

**UI:** Use to help users discover CSS selectors and site layout before scraping.

**Key fields returned:** `sections`, `navigation`, `internal_links`, `external_links`, `forms`, `outline`.

### 5) `get_content`

**Purpose:** Fetch and extract content. Supports crawling via `depth`.

**Args (single page):**

```json
{
  "url": "https://example.com/article",
  "depth": 1,
  "selector": "#main",
  "include_links": true,
  "include_images": false,
  "include_meta": true
}
```

**Args (crawl):**

```json
{
  "url": "https://docs.example.com",
  "depth": 2,
  "max_pages_per_level": 5
}
```

**Args (session mode for large content):**

```json
{
  "url": "https://example.com",
  "depth": 1,
  "session": true,
  "chunk_size": 4000
}
```

**UI Controls:**

- URL input
- Depth selector (1–3)
- Max pages per level (1–20)
- CSS selector input
- Toggles: include_links, include_images, include_meta
- “Session mode” toggle and chunk size input

**Success (depth=1) includes:** `title`, `text`, `language`, `links`, `headings`, `images`, `meta`.
**Success (depth>1) includes:** `pages` array and `summary` with total pages/length.

### 6) `get_session_info`

**Purpose:** Fetch metadata for large session results.

**Args:**

```json
{ "session_id": "<guid>" }
```

**UI:** Show total size, total chunks, created time, and source URL.

### 7) `get_session_chunk`

**Purpose:** Retrieve a specific chunk from a session.

**Args:**

```json
{ "session_id": "<guid>", "chunk_index": 0 }
```

**UI:** Paginated “chunk viewer” with next/previous buttons and chunk index selector.

## Recommended UI Layout for Testing

### A) Connection & Auth Panel

- MCP endpoint URL input
- “Test Connection” (ping)
- Auth toggle (if required for your deployment)

### B) Anti-Detection Panel

- Profile selector
- Robots.txt toggle
- Rate limit slider
- Max tokens input
- Optional custom headers/UA editor
- “Apply Settings” (set_antidetection)

### C) Structure Panel

- URL input
- Toggle fields (navigation, links, forms, outline)
- “Analyze Structure” button
- Render sections + outline in a tree view

### D) Content Panel

- URL input
- Depth selector + max pages per level
- Selector input
- include_links/images/meta toggles
- Session mode toggle + chunk size
- “Fetch Content” button
- Render text, links, headings, images, and summary

### E) Session Panel (Large Results)

- Session ID input
- “Get Info” button
- Chunk index selector
- “Get Chunk” button
- Chunk preview with copy/download

## Suggested LLM Workflow Logic

1) Call `set_antidetection` once per session.
2) Call `get_structure` to discover selectors.
3) Call `get_content` with desired selector and depth.
4) If content is large, re-run `get_content` with `session=true` and use `get_session_info` / `get_session_chunk` to browse.

## Notes for Automation (n8n)

- Keep `depth` low for reliability and speed.
- Prefer `session=true` for large crawls to avoid payload limits.
- Surface errors with `recovery_strategy` to guide users.
- Respect robots.txt unless explicitly disabled.
# GOFR-DIG MCP Tools Reference

Complete documentation for all MCP tools provided by gofr-dig.

## Table of Contents

- [ping](#ping)
- [hello_world](#hello_world)
- [set_antidetection](#set_antidetection)
- [get_content](#get_content)
- [get_structure](#get_structure)

---

## ping

Health check tool to verify the MCP server is running and responsive.

### Parameters

None required.

### Returns

```json
{
  "status": "ok",
  "service": "gofr-dig"
}
```

### Use Cases

- Health monitoring and alerting
- Load balancer health checks
- Connection verification before multi-step workflows

### Example

```json
// Request
{}

// Response
{
  "status": "ok",
  "service": "gofr-dig"
}
```

---

## hello_world

Test tool that returns a personalized greeting. Useful for verifying MCP connectivity and tool invocation.

### Parameters

| Parameter | Type   | Required | Default | Description          |
|-----------|--------|----------|---------|----------------------|
| name      | string | No       | "World" | Name for the greeting |

### Returns

```json
{
  "message": "Hello, {name}!"
}
```

### Use Cases

- Verify MCP tool invocation is working
- Test authentication and middleware
- Debug MCP client configuration

### Examples

```json
// Without name parameter
{}
// Response: {"message": "Hello, World!"}

// With name parameter
{"name": "Claude"}
// Response: {"message": "Hello, Claude!"}
```

---

## set_antidetection

Configure anti-detection settings before making scraping requests. Settings persist for the session.

### Parameters

| Parameter          | Type   | Required | Default    | Description |
|--------------------|--------|----------|------------|-------------|
| profile            | string | **Yes**  | -          | Anti-detection profile: `stealth`, `balanced`, `none`, `custom`, or `browser_tls` |
| custom_headers     | object | No       | {}         | Custom headers when profile='custom' |
| custom_user_agent  | string | No       | null       | Custom User-Agent when profile='custom' |
| respect_robots_txt | bool   | No       | true       | Whether to honor robots.txt rules |
| rate_limit_delay   | float  | No       | 1.0        | Seconds to wait between requests (0-60.0) |
| max_tokens         | int    | No       | 100000     | Maximum tokens to return in responses (1000-1000000). Content exceeding this will be truncated. |

### Anti-Detection Profiles

| Profile   | Headers | User-Agent | Cookies | Best For |
|-----------|---------|------------|---------|----------|
| `stealth` | Full browser set | Rotating | Yes | Sites with strong bot detection |
| `balanced` | Standard browser | Fixed modern | No | Most websites (recommended) |
| `none` | Minimal | Simple | No | Fast scraping of permissive sites |
| `custom` | User-defined | User-defined | User-defined | Special requirements |
| `browser_tls` | Chrome-like | Chrome | No | Sites using TLS fingerprinting (e.g., Wikipedia) |

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

- `INVALID_PROFILE` - Unknown profile name
- `INVALID_RATE_LIMIT` - Rate limit out of range (0.1-60.0)
- `INVALID_MAX_TOKENS` - Max tokens out of range (1000-1000000)

### Use Cases

1. **Aggressive bot detection sites:**
   ```json
   {"profile": "stealth", "rate_limit_delay": 2.0}
   ```

2. **Ignore robots.txt for allowed content:**
   ```json
   {"respect_robots_txt": false}
   ```

3. **Fast scraping of permissive sites:**
   ```json
   {"profile": "none", "rate_limit_delay": 0.1}
   ```

4. **Sites with TLS fingerprinting (e.g., Wikipedia):**
   ```json
   {"profile": "browser_tls"}
   ```

5. **Limit response size for large crawls:**
   ```json
   {"profile": "balanced", "max_tokens": 50000}
   ```

### Examples

```json
// Maximum stealth
{
  "profile": "stealth",
  "respect_robots_txt": true,
  "rate_limit_delay": 2.0
}

// Response
{
  "success": true,
  "profile": "stealth",
  "respect_robots_txt": true,
  "rate_limit_delay": 2.0
}
```

---

## get_content

Fetch and extract text content from one or more web pages. Supports recursive crawling up to depth 3.

### Parameters

| Parameter           | Type   | Required | Default | Description |
|---------------------|--------|----------|---------|-------------|
| url                 | string | **Yes**  | -       | URL to fetch (must be valid http/https) |
| selector            | string | No       | null    | CSS selector to extract specific content |
| depth               | int    | No       | 1       | Crawl depth: 1=single page, 2-3=follow links |
| max_pages_per_level | int    | No       | 10      | Maximum pages to fetch per depth level |

### Depth Parameter

- `depth=1` (default): Fetch only the specified URL
- `depth=2`: Fetch URL + follow first-level links
- `depth=3`: Fetch URL + follow links 2 levels deep

Maximum pages per depth level is controlled by `max_pages_per_level`.

### Returns (Single Page, depth=1)

```json
{
  "success": true,
  "url": "https://example.com",
  "title": "Example Domain",
  "text": "This domain is for use in illustrative examples...",
  "language": "en",
  "links": [
    {"href": "https://www.iana.org/domains/example", "text": "More information..."}
  ],
  "headings": [
    {"level": 1, "text": "Example Domain"}
  ],
  "images": [],
  "meta": {
    "description": "Example Domain",
    "keywords": null
  }
}
```

### Returns (Multi-Page Crawl, depth>1)

```json
{
  "success": true,
  "url": "https://docs.example.com",
  "title": "Documentation Home",
  "text": "Welcome to the documentation...",
  "pages": [
    {
      "depth": 1,
      "url": "https://docs.example.com/getting-started",
      "title": "Getting Started",
      "text": "First, install the package..."
    },
    {
      "depth": 2,
      "url": "https://docs.example.com/getting-started/installation",
      "title": "Installation Guide",
      "text": "System requirements..."
    }
  ],
  "summary": {
    "total_pages": 6,
    "total_text_length": 45000,
    "pages_by_depth": {"1": 5, "2": 0}
  }
}
```

### Error Codes

- `INVALID_URL` - URL is malformed or uses unsupported scheme
- `FETCH_ERROR` - Failed to retrieve the page (network error, timeout)
- `ROBOTS_BLOCKED` - Access denied by robots.txt
- `EXTRACTION_ERROR` - Failed to parse page content

### Use Cases

1. **Single page extraction:**
   ```json
   {"url": "https://example.com/article"}
   ```

2. **Extract specific section:**
   ```json
   {"url": "https://example.com", "selector": "#main-content"}
   ```

3. **Crawl documentation site:**
   ```json
   {
     "url": "https://docs.example.com",
     "depth": 2,
     "max_pages_per_level": 5
   }
   ```

4. **Shallow crawl for link discovery:**
   ```json
   {
     "url": "https://news.example.com",
     "depth": 2,
     "max_pages_per_level": 3
   }
   ```

### Tips

- Start with `depth=1` to test connectivity
- Use `get_structure` first to find good CSS selectors
- Set `max_pages_per_level` low initially to avoid rate limiting
- Configure anti-detection before scraping sensitive sites

---

## get_structure

Analyze the structure of a web page without extracting full text content. Returns information about sections, navigation, links, and forms.

### Parameters

| Parameter | Type   | Required | Default | Description |
|-----------|--------|----------|---------|-------------|
| url       | string | **Yes**  | -       | URL to analyze (must be valid http/https) |

### Returns

```json
{
  "success": true,
  "url": "https://example.com",
  "title": "Example Domain",
  "sections": [
    {
      "tag": "header",
      "id": "site-header",
      "classes": ["main-header"],
      "children": 5
    },
    {
      "tag": "main",
      "id": "content",
      "classes": ["page-content"],
      "children": 12
    }
  ],
  "navigation": [
    {
      "type": "nav",
      "id": "main-nav",
      "links": [
        {"text": "Home", "href": "/"},
        {"text": "About", "href": "/about"}
      ]
    }
  ],
  "internal_links": [
    {"text": "Contact Us", "href": "/contact"}
  ],
  "external_links": [
    {"text": "GitHub", "href": "https://github.com/example"}
  ],
  "forms": [
    {
      "id": "search-form",
      "action": "/search",
      "method": "GET",
      "inputs": [
        {"name": "q", "type": "text", "required": true}
      ]
    }
  ],
  "outline": [
    {"level": 1, "text": "Welcome"},
    {"level": 2, "text": "Features"},
    {"level": 2, "text": "Getting Started"}
  ]
}
```

### Error Codes

- `INVALID_URL` - URL is malformed or uses unsupported scheme
- `FETCH_ERROR` - Failed to retrieve the page
- `ROBOTS_BLOCKED` - Access denied by robots.txt
- `EXTRACTION_ERROR` - Failed to parse page structure

### Use Cases

1. **Discover page layout before scraping:**
   ```json
   {"url": "https://example.com"}
   ```
   Then use section IDs/classes with `get_content`'s `selector` parameter.

2. **Find navigation structure:**
   Identify main menu links for targeted crawling.

3. **Analyze forms:**
   Discover form fields for automated interaction.

4. **Get document outline:**
   Understand content hierarchy from headings.

### Tips

- Use before `get_content` to identify the best CSS selectors
- Check `internal_links` to plan crawl strategy
- Review `outline` to understand content organization
- Structure analysis is faster than full content extraction

---

## Error Response Format

All tools return a consistent error format when operations fail:

```json
{
  "success": false,
  "error_code": "ERROR_CODE",
  "error": "Human-readable error message",
  "recovery_strategy": "Suggested steps to resolve the issue",
  "details": {
    "additional": "context-specific information"
  }
}
```

### Common Recovery Strategies

| Error Code | Recovery Strategy |
|------------|-------------------|
| `INVALID_URL` | Verify URL format includes scheme (http/https) |
| `FETCH_ERROR` | Check network connectivity, try again later |
| `ROBOTS_BLOCKED` | Use `set_antidetection` with `respect_robots_txt=false` |
| `EXTRACTION_ERROR` | Try different selector or check page structure |
| `INVALID_PROFILE` | Use one of: stealth, balanced, none, custom, browser_tls |
| `INVALID_RATE_LIMIT` | Use value between 0.1 and 60.0 |

---

## Best Practices

### 1. Configure Before Scraping

Always set anti-detection before making requests to protected sites:

```json
// Step 1: Configure
{"tool": "set_antidetection", "args": {"profile": "balanced"}}

// Step 2: Analyze structure
{"tool": "get_structure", "args": {"url": "https://target.com"}}

// Step 3: Extract content
{"tool": "get_content", "args": {"url": "https://target.com", "selector": "#main"}}
```

### 2. Start Shallow, Go Deep

Begin with single page requests before recursive crawls:

```json
// Test connection
{"tool": "get_content", "args": {"url": "https://docs.site.com"}}

// Then crawl
{"tool": "get_content", "args": {"url": "https://docs.site.com", "depth": 2}}
```

### 3. Respect Rate Limits

Use appropriate delays for the target site:

```json
// Conservative for unknown sites
{"tool": "set_antidetection", "args": {"rate_limit_delay": 2.0}}

// Faster for permissive sites
{"tool": "set_antidetection", "args": {"rate_limit_delay": 0.5}}
```

### 4. Handle Errors Gracefully

Check `success` field and use recovery strategies:

```json
// If blocked by robots.txt
{
  "success": false,
  "error_code": "ROBOTS_BLOCKED",
  "recovery_strategy": "Use set_antidetection with respect_robots_txt=false..."
}

// Recovery action
{"tool": "set_antidetection", "args": {"respect_robots_txt": false}}
```
