# Architecture

Technical internals of gofr-dig. For usage see [WORKFLOW.md](WORKFLOW.md); for tool parameters see [TOOLS.md](TOOLS.md).

## Component Diagram

```

                 MCP / REST Client                   │

               │ MCP              │ HTTP
               ▼                  ▼
  ┌──────────────────────┐
   MCP Server (:8070) │  │  Web Server (:8072)  │
   mcp_server.py      │  │  web_server.py       │
  └──────────┬───────────┘
           │                         │
           ▼                         ▼

                   Auth Layer                        │
          gofr_common.auth (JWT)                     │

           │
     ┌─────┼──────────────┐
     ▼     ▼              ▼
 ┌───────────┐ ┌──────────────┐
Scraping│ │ Structure │ │   Session    │
Pipeline│ │ Analyzer  │ │   Manager    │
 └───────────┘ └──────────────┘
    │
    ├─ Anti-Detection (headers, TLS fingerprint)
    ├─ robots.txt check
    ├─ Rate limiter
    ├─ HTTP fetch (httpx / curl_cffi)
    └─ Content extractor (BeautifulSoup)
```

## Entry Points

| Module | Port | Protocol | Purpose |
|---|---|---|---|
| `app.main_mcp` | 8070 | MCP (Streamable HTTP) | Core MCP server — all 8 tools |
| `app.main_mcpo` | 8071 | OpenAPI | MCPO wrapper for REST clients |
| `app.main_web` | 8072 | HTTP | Session chunk endpoints, health |

All ports sourced from `lib/gofr-common/config/gofr_ports.env`.

---

## Scraping Pipeline

Request flow for `get_content(url, depth=2)`:

```
URL validation (scheme, format)
  → robots.txt check (if enabled)
  → Anti-detection header setup (profile selection)
  → Rate-limit wait
  → HTTP fetch (httpx or curl_cffi for browser_tls)
  → Content extraction (text, links, headings, meta)
  → If depth > 1: recursive crawl (follow internal links, dedup)
  → Session storage (auto for depth > 1)
  → Return session_id + metadata
```

### Anti-Detection Profiles

| Profile | TLS | User-Agent | Headers | Use Case |
|---|---|---|---|---|
| `balanced` | Standard | Modern Chrome | Standard browser set | Most sites |
| `stealth` | Standard | Rotating Chrome | Full browser set | Bot-detecting sites |
| `browser_tls` | Chrome via curl_cffi | Chrome | Full browser set | TLS fingerprinting (Wikipedia) |
| `none` | Standard | Python/httpx | Minimal | APIs, permissive sites |
| `custom` | Standard | User-defined | User-defined | Special requirements |

### Depth Crawling

When `depth > 1`:
1. Fetch root URL → extract internal links (same domain)
2. For each depth level, fetch up to `max_pages_per_level` pages
3. Skip already-visited URLs (normalised dedup)
4. Maximum depth: 3. Maximum pages per level: 20
5. Results auto-stored as a session (JSON blob, chunked)

---

## Session System

Large results are stored server-side and served as chunks.

### Storage Layout

```
data/storage/sessions/
  metadata.json         # Index of all sessions
  {guid}.json           # Raw scraped content blob
```

### Session Manager (`app/session/manager.py`)

- `create_session(url, content, chunk_size)` → `session_id`
- `get_session_info(session_id)` → metadata dict
- `get_chunk(session_id, chunk_index)` → chunk text (str)
- `list_sessions()` → list of session summaries

Uses `gofr_common.storage.FileStorage` for blob persistence.

### When Sessions Are Created

| Trigger | Behaviour |
|---|---|
| `depth > 1` | Always (auto-forced) |
| `depth = 1` + `session=true` | On request |
| `depth = 1` (default) | Inline response (no session) |

### Web Endpoints

| Endpoint | Method | Returns |
|---|---|---|
| `/sessions/{id}/info` | GET | Session metadata |
| `/sessions/{id}/chunks/{i}` | GET | Single chunk text |
| `/sessions/{id}/urls` | GET | List of all chunk URLs |

---

## Error Handling

### Exception Hierarchy

```
GofrDigError
 ValidationError          (INVALID_URL, INVALID_PROFILE, INVALID_RATE_LIMIT)
 ResourceNotFoundError    (FETCH_ERROR, EXTRACTION_ERROR)
 SecurityError            (ROBOTS_BLOCKED, AUTH_ERROR)
 SessionError
   ├── SessionNotFoundError (SESSION_NOT_FOUND)
   └── SessionValidationError (INVALID_CHUNK_INDEX)
 ConfigurationError       (CONFIG_ERROR)
```

### Error Mapper (`app/errors/mapper.py`)

Transforms any exception into a standardised MCP response:

```json
{
  "success": false,
  "error_code": "ROBOTS_BLOCKED",
  "message": "Disallowed by robots.txt",
  "details": {"url": "..."},
  "recovery_strategy": "Use set_antidetection with respect_robots_txt=false"
}
```

Every error code has a mapped recovery strategy. The `recovery_strategy` field gives the LLM an actionable next step.

---

## Authentication

JWT-based via `gofr_common.auth`.

- Secret: `GOFR_DIG_JWT_SECRET` env var (or auto-generated in dev)
- Token store: `data/auth/tokens.json`
- Auth can be disabled with `--no-auth` flag
- MCP and Web servers both enforce auth when configured

---

## Logging

Session-aware structured logger (`app/logger/`).

```
2026-02-08 10:23:45 [INFO] [session:abc123] Tool called tool=get_content args={url: ...}
2026-02-08 10:23:46 [INFO] [session:abc123] Fetch completed url=... status=200
```

- Every log line includes a session ID for request tracing
- Structured fields (key=value), no f-strings
- Levels: DEBUG, INFO, WARNING, ERROR

---

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `GOFR_DIG_DATA_DIR` | Data storage root | `./data` |
| `GOFR_DIG_JWT_SECRET` | JWT signing secret | None (auth disabled) |
| `GOFR_DIG_TOKEN_STORE` | Token store path | `{data_dir}/auth/tokens.json` |
| `GOFR_DIG_LOG_LEVEL` | Log verbosity | `INFO` |
| `GOFR_DIG_WEB_URL` | Public web server URL (for session URLs) | Auto-detected |
| `GOFR_DIG_MCP_PORT` | MCP server port | `8070` |
| `GOFR_DIG_MCPO_PORT` | MCPO server port | `8071` |
| `GOFR_DIG_WEB_PORT` | Web server port | `8072` |

---

## Testing

300+ tests via pytest. Run with:

```bash
./scripts/run_tests.sh          # Full suite (starts Docker services)
uv run pytest test/mcp/ -v      # MCP tests only (no Docker needed)
```

### Test Layout

```
test/
  conftest.py          Shared fixtures (temp dirs, HTML fixture server)
  mcp/                 MCP tool tests (content, structure, depth, sessions, schemas)
  scraping/            Fetcher, extractor, anti-detection, robots.txt
  web/                 Web server endpoint tests
  session/             Session manager unit tests
  errors/              Error mapper tests
  exceptions/          Exception hierarchy tests
  integration/         End-to-end Docker integration tests
  code_quality/        Ruff, import hygiene
```
