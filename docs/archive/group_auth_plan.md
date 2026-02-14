# Group-Based Session Access — Implementation Plan

## Goal

Enforce that sessions created via a token are **owned by the token's first group**, and only tokens whose group list contains that group can read the session data.

```
Permission model:  group → session (1:many)

CREATE:  token.groups[0]  →  session.group = "myteam"
READ:    token.groups      ∩  session.group ≠ ∅  →  allow
         token.groups      ∩  session.group = ∅  →  403
```

## Auth Delivery — Two Paths

MCP tool calls go through the MCPO proxy, which does **not** reliably forward HTTP headers into individual tool invocations. Therefore:

| Path | Auth mechanism | Used by |
|------|---------------|---------|
| **MCP tools** | `auth_tokens` tool parameter (list of JWT strings) | MCPO proxy, MCP clients, N8N |
| **Web REST endpoints** | `Authorization: Bearer <jwt>` header | Direct HTTP calls to `/sessions/*` |

The `auth_tokens` parameter is the **primary** mechanism for MCP. HTTP Authorization headers are only used for direct web server REST calls.

### Resolution Priority

```
MCP tool call:
  1. auth_tokens parameter  →  verify each, union groups
  2. No auth_tokens          →  anonymous (group=None → "public")

Web REST call:
  1. Authorization header    →  verify token, extract groups
  2. No header               →  anonymous (group=None → "public")
```

## Current State

| Component | Built? | Wired? |
|-----------|--------|--------|
| JWT tokens carry `groups` claim | ✅ | ✅ |
| `TokenInfo.groups`, `has_group()`, `has_any_group()` | ✅ | ✅ |
| `AuthService.verify_token()` → `TokenInfo` | ✅ | ✅ Called in `_resolve_group_from_tokens` and `_resolve_group` |
| `AuthHeaderMiddleware` (captures `Authorization` into ContextVar) | ✅ | N/A (not needed — web uses `_resolve_group(request)`) |
| `SessionManager.create_session(group=...)` | ✅ | ✅ Passed from `_handle_get_content` |
| `SessionManager.get_session_info(group=...)` / `get_chunk(group=...)` | ✅ | ✅ Passed from all session handlers |
| `PermissionDeniedError` raised by SessionManager on group mismatch | ✅ | ✅ Caught → `PERMISSION_DENIED` (MCP) / 403 (web) |

**Status: ✅ COMPLETE** — All steps implemented and tested (363 unit tests passing).

---

## Steps

### Step 1 — Add `auth_tokens` Parameter to MCP Tool Schemas

**File:** `app/mcp_server/mcp_server.py` — `handle_list_tools()`

Add `auth_tokens` to every tool's `inputSchema.properties` (except `ping`):

```python
"auth_tokens": {
    "type": "array",
    "items": {"type": "string"},
    "description": (
        "One or more JWT tokens for authentication. "
        "The server verifies each token and uses the first group "
        "from the first valid token to scope session access. "
        "Omit for anonymous/public access."
    ),
},
```

This makes auth explicit and discoverable in the tool schema — LLMs and automation services can see exactly how to authenticate.

---

### Step 2 — Add a Token Resolution Helper for MCP Tools

**File:** `app/mcp_server/mcp_server.py` (new helper near `get_session_manager`)

```python
from gofr_common.auth.exceptions import AuthError

def _resolve_group_from_tokens(auth_tokens: list[str] | None) -> str | None:
    """Resolve the primary group from auth_tokens passed as a tool parameter.

    Returns the first group from the first valid token, or None if
    auth is disabled or no tokens provided.

    Raises AuthError (401/403) if tokens are provided but all are invalid.
    """
    if auth_service is None:
        return None                          # auth disabled (--no-auth)

    if not auth_tokens:
        return None                          # anonymous → public

    last_error: AuthError | None = None
    for raw_token in auth_tokens:
        # Strip "Bearer " prefix if present
        if raw_token.lower().startswith("bearer "):
            raw_token = raw_token[7:].strip()
        else:
            raw_token = raw_token.strip()

        if not raw_token:
            continue

        try:
            token_info = auth_service.verify_token(raw_token)
            if token_info.groups:
                return token_info.groups[0]  # primary group = first in list
        except AuthError as e:
            last_error = e
            continue                         # try next token

    # All tokens failed
    if last_error:
        raise last_error
    return None
```

**Key design:** This reads from the `arguments` dict, not from a ContextVar/header. No middleware needed on the MCP server.

---

### Step 3 — Wire Group into Session-Creating Tools

**File:** `app/mcp_server/mcp_server.py` — `_handle_get_content`

At the **top** of the handler (after argument parsing):

```python
auth_tokens = arguments.get("auth_tokens")
group = _resolve_group_from_tokens(auth_tokens)
```

Then pass `group` to both `create_session` call sites:

```python
# depth=1 session path
session_id = manager.create_session(
    url=url, content=page_data, chunk_size=c_size, group=group,
)

# depth>1 session path
session_id = manager.create_session(
    url=url, content=results, chunk_size=c_size, group=group,
)
```

**Effect:** Sessions are tagged with the token's primary group. Anonymous requests (no `auth_tokens` / auth disabled) create sessions with `group=None` (global).

---

### Step 4 — Wire Group into Session-Reading Tools

**File:** `app/mcp_server/mcp_server.py`

Add the same two lines at the top of each session handler:

```python
auth_tokens = arguments.get("auth_tokens")
group = _resolve_group_from_tokens(auth_tokens)
```

Then pass `group` through:

| Handler | Current Call | New Call |
|---------|-------------|----------|
| `_handle_get_session_info` | `manager.get_session_info(session_id)` | `manager.get_session_info(session_id, group=group)` |
| `_handle_get_session_chunk` | `manager.get_chunk(session_id, idx)` | `manager.get_chunk(session_id, idx, group=group)` |
| `_handle_list_sessions` | `manager.list_sessions()` | `manager.list_sessions(group=group)` |
| `_handle_get_session_urls` | `manager.get_session_info(session_id)` | `manager.get_session_info(session_id, group=group)` |

Also add `auth_tokens` to `_handle_set_antidetection` and `_handle_get_structure` for consistency (extract group for logging/auditing even though these tools don't use sessions).

**Effect:** `SessionManager` enforces group match → `PermissionDeniedError` on mismatch. `list_sessions` returns only sessions visible to the caller's group.

---

### Step 5 — Map Auth and Permission Errors to MCP Responses

**File:** `app/errors/mapper.py`

Add recovery strategies:

```python
"AUTH_ERROR": "Provide a valid JWT token in the auth_tokens parameter.",
"PERMISSION_DENIED": "Your token's groups do not include the group that owns this session.",
```

**File:** `app/mcp_server/mcp_server.py`

In each session handler's except chain, catch these:

```python
except AuthError as e:
    return _error_response(
        "AUTH_ERROR", str(e),
        recovery_strategy="Provide a valid JWT in the auth_tokens parameter.",
    )
except PermissionDeniedError as e:
    return _error_response(
        "PERMISSION_DENIED", str(e),
        recovery_strategy="Use a token whose groups include the session's owner group.",
    )
```

Consider a shared decorator `_with_auth_errors` to avoid repeating this in every handler.

---

### Step 6 — Wire Auth into Web Server REST Endpoints (Header-Based)

**File:** `app/web_server/web_server.py`

The web server serves direct REST calls (not through MCPO), so it uses the standard **Authorization header**.

**6a.** Enable auth middleware on the web server's Starlette app:

```python
include_auth_middleware=bool(self.auth_service)
```

**6b.** Add a `_resolve_group(self, request)` method:

```python
def _resolve_group(self, request) -> str | None:
    if self.auth_service is None:
        return None
    auth_header = request.headers.get("authorization", "")
    if not auth_header:
        return None
    raw = auth_header.removeprefix("Bearer ").strip()
    if not raw:
        return None
    token_info = self.auth_service.verify_token(raw)
    return token_info.groups[0] if token_info.groups else None
```

**6c.** Call it at the top of each session endpoint and pass `group=group` to all `SessionManager` calls.

**6d.** Catch `AuthError` → 401 JSON, `PermissionDeniedError` → 403 JSON.

---

### Step 7 — Handle Anonymous / No-Auth Mode

Backwards-compatible behaviour:

| Scenario | `auth_service` | `auth_tokens` / Header | Group | Session access |
|----------|---------------|------------------------|-------|---------------|
| `--no-auth` flag | `None` | Ignored | `None` | All sessions |
| Auth enabled, no token | Set | Not provided | `None` | Global sessions only |
| Auth enabled, valid token | Set | `["eyJ..."]` | `groups[0]` | Group + global sessions |
| Auth enabled, invalid token | Set | `["bad..."]` | — | 401 error |

**`group=None` sessions are world-readable.** Anonymous sessions have no owner and can be read by anyone. Only group-owned sessions enforce access.

---

### Step 8 — Tests

| Test | What it verifies |
|------|-----------------|
| **No `auth_tokens` → session created with `group=None`** | Anonymous access works |
| **`auth_tokens=["team-a-jwt"]` → session tagged `"team-a"`** | Group extraction + create |
| **`"team-a"` token reads `"team-a"` session → 200** | Group match allows read |
| **`"team-b"` token reads `"team-a"` session → 403** | Group mismatch blocks read |
| **Token with `groups=["team-a", "team-b"]` reads `"team-a"` session → 200** | Any group in list works |
| **Invalid `auth_tokens` → AUTH_ERROR** | Auth error propagation |
| **`list_sessions` with `"team-a"` token → only `"team-a"` + global sessions** | Group-scoped listing |
| **`--no-auth` mode → all sessions accessible** | Backwards compatibility |
| **Web `Authorization: Bearer …` with wrong group → 403** | Web header-based enforcement |
| **Web no header → only global sessions** | Web anonymous access |

---

## File Change Summary

| File | Changes |
|------|---------|
| `app/mcp_server/mcp_server.py` | Add `auth_tokens` to tool schemas, add `_resolve_group_from_tokens()`, pass `group` to all session ops, catch auth/permission errors |
| `app/web_server/web_server.py` | Enable auth middleware, add `_resolve_group()`, pass `group` to all session ops, add error handling |
| `app/errors/mapper.py` | Add `AUTH_ERROR` and `PERMISSION_DENIED` recovery strategies |
| `test/mcp/test_session_auth.py` | New: group-scoped session access via `auth_tokens` param |
| `test/web/test_web_session_auth.py` | New: web endpoint group enforcement via `Authorization` header |

**No changes needed to:**
- `gofr_common` (auth, middleware, storage — all already support this)
- `app/session/manager.py` (already accepts and enforces `group`)
- `app/main_mcp.py` / `app/main_web.py` (auth_service already created and injected)

---

## Execution Order

Steps 1–5 as a single unit (MCP server auth). Step 6 follows (web server auth). Step 7 is design validation (no code). Step 8 spans both.

**Estimated scope:** ~100 lines changed, ~200 lines of new tests.

---

## Implementation Complete

All 8 steps implemented and verified:

| Step | Description | Status |
|------|-------------|--------|
| 1 | `auth_tokens` in all 7 tool schemas (AUTH_TOKENS_SCHEMA constant) | ✅ |
| 2 | `_resolve_group_from_tokens()` helper | ✅ |
| 3 | `group` wired into `get_content` session creation (depth=1 + depth>1) | ✅ |
| 4 | `group` wired into `get_session_info`, `get_session_chunk`, `list_sessions`, `get_session_urls` | ✅ |
| 5 | `AUTH_ERROR` + `PERMISSION_DENIED` error mapping + catch blocks | ✅ |
| 6 | Web server auth (`_resolve_group()`, group passthrough, 401/403 handling) | ✅ |
| 7 | Anonymous/no-auth mode (inherent — `group=None` flows through) | ✅ |
| 8 | Auth tests: 16 MCP tests + 11 web tests | ✅ |

**Test results:** 363 passed, 33 deselected (integration tests skipped in unit mode).