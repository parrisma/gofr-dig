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
- [Error Codes](#error-codes)

## Mini Spec: JWT Handling (MCP, MCPO, Web)

This section defines auth behavior for these MCP tools:

- `get_content`
- `get_structure`
- `get_session_info`
- `get_session_chunk`
- `list_sessions`
- `get_session_urls`
- `get_session`

### API Authority Model

- MCP is the **master API** and source of truth for capability semantics.
- MCPO and Web are **auxiliary access paths** that expose the same capabilities.
- Capability behavior should stay aligned across all three surfaces:
  - same auth intent (public fallback + token override rules)
  - same effective authorization scope (group 0 = primary group)
  - same effective success/error outcomes (transport envelope may differ)

### MCP Tool Contract

- Each auth-aware MCP tool accepts optional `auth_token`:

```json
"auth_token": {
  "type": "string",
  "description": "JWT token for authentication"
}
```

- `auth_token` is optional. Omitting it means public/anonymous access.
- `ping` remains unauthenticated and does not accept `auth_token`.
- If the token contains multiple groups, group index `0` is used as the effective scope.

### MCP Token Resolution

For MCP tool calls:

1. `arguments.auth_token` (if present)
2. Public/anonymous access

Rules:

- If a token is provided but invalid, return `AUTH_ERROR`.
- If no token is provided, do **not** return auth error; continue as public.
- If server runs with `--no-auth`, token verification is bypassed.

### MCPO Behavior

MCPO is an adapter over MCP and should preserve MCP semantics.

- MCPO may pass an incoming `Authorization` header through to MCP transport.
- If MCPO is configured with a static startup token, it may use that token when no caller token is present.
- MCP tool-level auth semantics remain governed by MCP (`auth_token` argument and server auth mode).

### Web API Behavior

Web is an auxiliary HTTP access path for sessions and should preserve MCP access semantics.

For web session endpoints (`/sessions/...`):

- Auth is accepted from header only:

```http
Authorization: Bearer <JWT_TOKEN>
```

- Query parameter auth is not supported.
- If token includes multiple groups, group index `0` is the primary group.

### Token Expiry

Token expiry and validation behavior are handled by `gofr_common` auth services.

## Security Defaults

### SSRF Protection

Outgoing URL fetches are validated to block private/internal targets.

Blocked by default:

- RFC1918 IPv4 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
- loopback/link-local and metadata-like targets
- equivalent IPv6 private/link-local/loopback ranges

When blocked, tools return `SSRF_BLOCKED`.

### Robots.txt Enforcement

- `robots.txt` is always respected.
- There is no tool option to disable `robots.txt` checks.

### Inbound Rate Limiting

MCP tool calls are protected by an inbound rate limiter.

Environment variables:

- `GOFR_DIG_RATE_LIMIT_CALLS` (default: `60`)
- `GOFR_DIG_RATE_LIMIT_WINDOW` in seconds (default: `60`)

When exceeded, tools return `RATE_LIMIT_EXCEEDED`.

## Behavior Notes

### Session-Scoped Settings

`set_antidetection` updates scraping settings that persist for the active MCP server process/session context and affect subsequent fetch tools.

### Response Size Control

`max_response_chars` is a character limit (not token limit). Large inline content is truncated by character count.

### Response Type Contract

`get_content` responses include:

- `response_type: "inline"` when content is returned directly
- `response_type: "session"` when server stores content and returns `session_id`

### Base URL Auto-Detection

`get_session_urls` can auto-detect base URL from `GOFR_DIG_WEB_URL`.

If not set, fallback host/port inference can be fragile in containerized/proxy setups. For deterministic links, provide `base_url` explicitly or set `GOFR_DIG_WEB_URL`.

## Commands

### `ping`
Checks if the service is running.

Returns:

- `{"status":"ok","service":"gofr-dig"}`

---

### `set_antidetection`
Configures scraping profile and request behavior.

Parameters:

- `profile` (string, required):
  - `balanced` (default)
  - `stealth`
  - `browser_tls`
  - `none`
  - `custom`
- `custom_headers` (object, optional): used with `profile="custom"`
- `custom_user_agent` (string, optional): used with `profile="custom"`
- `rate_limit_delay` (number, optional): seconds between outbound requests (`0` to `60`, default `1.0`)
- `max_response_chars` (integer, optional): response size cap (`4000` to `4000000`, default `400000`)
- `auth_token` (string, optional)

Notes:

- `robots.txt` is always enforced.
- `max_response_chars` applies to downstream content-returning tools.

---

### `get_content`
Fetches page content (single page or recursive crawl).

Parameters:

- `url` (string, required)
- `depth` (integer, optional): `1` to `3` (default `1`)
- `max_pages_per_level` (integer, optional): `1` to `20` (default `5`)
- `selector` (string, optional): extract only matching section
- `include_links` (boolean, optional, default `true`)
- `include_images` (boolean, optional, default `false`)
- `include_meta` (boolean, optional, default `true`)
- `filter_noise` (boolean, optional, default `true`)
- `session` (boolean, optional, default `false`): control session storage. `true` stores results server-side and returns a `session_id`. `false` (default) returns all content inline. Parameters are honored exactly — no auto-override.
- `chunk_size` (integer, optional): chunk size used when session storage is active
- `max_bytes` (integer, optional, default `5242880`): maximum inline response size in bytes. Returns `CONTENT_TOO_LARGE` if exceeded.
- `timeout_seconds` (number, optional): fetch timeout per URL (default `60`)
- `auth_token` (string, optional)

Response behavior:

- Returns `response_type="inline"` for direct content (default).
- Returns `response_type="session"` with `session_id` when `session=true`.
- All parameters are honored exactly as sent — no auto-overrides.

Chunk size guidance:

- Recommended `chunk_size`: `3000`–`8000` chars
- Good default: `4000`
- Smaller chunks improve incremental processing but increase total chunk count.

---

### `get_structure`
Analyzes layout without extracting full text.

Parameters:

- `url` (string, required)
- `selector` (string, optional): scope structural analysis to a section
- `include_navigation` (boolean, optional, default `true`)
- `include_internal_links` (boolean, optional, default `true`)
- `include_external_links` (boolean, optional, default `true`)
- `include_forms` (boolean, optional, default `true`)
- `include_outline` (boolean, optional, default `true`)
- `timeout_seconds` (number, optional): fetch timeout per URL (default `60`)
- `auth_token` (string, optional)

---

### `get_session_info`
Gets metadata for a stored scraping session.

Parameters:

- `session_id` (string, required)
- `auth_token` (string, optional)

---

### `get_session_chunk`
Retrieves one chunk from a stored session.

Parameters:

- `session_id` (string, required)
- `chunk_index` (integer, required)
- `auth_token` (string, optional)

---

### `list_sessions`
Lists stored sessions accessible to the resolved group/public scope.

Parameters:

- `auth_token` (string, optional)

---

### `get_session_urls`
Returns chunk references as JSON descriptors or plain HTTP URLs.

Parameters:

- `session_id` (string, required)
- `as_json` (boolean, optional, default `true`)
- `base_url` (string, optional): used when `as_json=false`
- `auth_token` (string, optional)

---

### `get_session`
Retrieves all chunks joined into one text payload.

Parameters:

- `session_id` (string, required)
- `max_bytes` (integer, optional, default `5242880`)
- `timeout_seconds` (number, optional, default `60`): timeout for retrieving and joining chunks
- `auth_token` (string, optional)

## Error Codes

Standard MCP-style error shape:

```json
{
  "success": false,
  "error_code": "SOME_CODE",
  "message": "Human-readable message",
  "details": {},
  "recovery_strategy": "How to fix"
}
```

### Full Error Table

| Error Code | Meaning | Typical Recovery |
|---|---|---|
| `INVALID_URL` | Missing/invalid URL | Use full `http://` or `https://` URL |
| `URL_NOT_FOUND` | Target returned 404 | Verify URL exists |
| `FETCH_ERROR` | Generic fetch failure | Retry and verify target availability |
| `TIMEOUT_ERROR` | Request timed out | Increase timeout or retry later |
| `CONNECTION_ERROR` | DNS/network/connectivity failure | Verify hostname/network |
| `ROBOTS_BLOCKED` | Access denied by robots rules | Choose allowed URL/path |
| `ACCESS_DENIED` | Target denied request | Adjust profile/headers |
| `RATE_LIMITED` | Outbound target rate-limited | Increase `rate_limit_delay` |
| `RATE_LIMIT_EXCEEDED` | Inbound MCP call rate limit exceeded | Wait for reset window |
| `SSRF_BLOCKED` | URL resolved to private/internal target | Use public target URL |
| `SELECTOR_NOT_FOUND` | Selector matched no elements | Validate selector against page structure |
| `INVALID_SELECTOR` | Invalid CSS selector syntax | Fix selector syntax |
| `EXTRACTION_ERROR` | Content/structure parsing failed | Retry with different selector/profile |
| `ENCODING_ERROR` | Character encoding issue | Retry with simpler extraction path |
| `INVALID_PROFILE` | Unknown anti-detection profile | Use supported profile values |
| `INVALID_HEADERS` | Malformed custom headers | Provide string key/value pairs |
| `INVALID_RATE_LIMIT` | Invalid `rate_limit_delay` value | Use non-negative seconds |
| `MAX_DEPTH_EXCEEDED` | Crawl depth beyond supported max | Use depth up to `3` |
| `MAX_PAGES_EXCEEDED` | Pages-per-level too high | Reduce `max_pages_per_level` |
| `UNKNOWN_TOOL` | Tool name not found | Call a listed tool |
| `INVALID_ARGUMENT` | Missing/invalid argument | Match tool input schema |
| `INVALID_MAX_RESPONSE_CHARS` | Invalid size cap | Use `4000` to `4000000` |
| `AUTH_ERROR` | Invalid/expired token | Provide valid JWT |
| `PERMISSION_DENIED` | Cross-group/session access denied | Use token for owning group |
| `SESSION_ERROR` | Session operation failed | Verify session exists and scope is correct |
| `SESSION_NOT_FOUND` | Session id not found | Use `list_sessions` or create a new session |
| `INVALID_CHUNK_INDEX` | Chunk index out of range | Check `total_chunks` via `get_session_info` |
| `CONFIGURATION_ERROR` | Server config issue | Check deployment/env configuration |
| `CONTENT_TOO_LARGE` | Joined session exceeds `max_bytes` | Use chunked retrieval instead |
