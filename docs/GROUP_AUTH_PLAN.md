# Group-Based Session Access — Implementation Plan

## Goal

Enforce that sessions created via a token are **owned by the token's first group**, and only tokens whose group list contains that group can read the session data.

```
Permission model:  group → session (1:many)

CREATE:  token.groups[0]  →  session.group = "myteam"
READ:    token.groups      ∩  session.group ≠ ∅  →  allow
         token.groups      ∩  session.group = ∅  →  403
```

## Current State

| Component | Built? | Wired? |
|-----------|--------|--------|
| JWT tokens carry `groups` claim | ✅ | — |
| `TokenInfo.groups`, `has_group()`, `has_any_group()` | ✅ | — |
| `AuthService.verify_token()` → `TokenInfo` | ✅ | ❌ Never called |
| `AuthHeaderMiddleware` (captures `Authorization` header into ContextVar) | ✅ | ❌ Not enabled |
| `SessionManager.create_session(group=...)` | ✅ | ❌ `group` never passed |
| `SessionManager.get_session_info(group=...)` / `get_chunk(group=...)` | ✅ | ❌ `group` never passed |
| `PermissionDeniedError` raised by SessionManager on group mismatch | ✅ | ❌ Not caught/mapped |
| `create_mcp_starlette_app(include_auth_middleware=...)` | ✅ | ❌ Defaults to `False` |

**Bottom line:** Every layer of infra exists. The only work is wiring them together in the request path.

---

## Steps

### Step 1 — Enable Auth Middleware on MCP Server

**File:** `app/mcp_server/mcp_server.py` (~L1311)

Pass `include_auth_middleware=True` when `auth_service` is set:

```python
starlette_app = create_mcp_starlette_app(
    mcp_handler=handle_streamable_http,
    lifespan=lifespan,
    env_prefix="GOFR_DIG",
    include_auth_middleware=bool(auth_service),   # ← NEW
)
```

This activates `AuthHeaderMiddleware`, which captures the `Authorization` header into the `_auth_header_context` ContextVar on every HTTP request.

**When `auth_service` is `None` (--no-auth mode):** middleware is not added, all requests proceed unauthenticated — preserving dev/test behaviour.

---

### Step 2 — Add a Token Resolution Helper

**File:** `app/mcp_server/mcp_server.py` (new helper near top, after `get_session_manager`)

```python
from gofr_common.web.middleware import get_auth_header_from_context
from gofr_common.auth.exceptions import AuthError

def _resolve_token_group() -> str | None:
    """Extract the primary group from the current request's auth token.

    Returns the first group from the token's group list, or None if
    auth is disabled or no token is present.

    Raises AuthError (401/403) if a token is present but invalid.
    """
    if auth_service is None:
        return None                          # auth disabled (--no-auth)

    header = get_auth_header_from_context()
    if not header:
        return None                          # no token sent → anonymous

    # Strip "Bearer " prefix
    if header.lower().startswith("bearer "):
        raw_token = header[7:].strip()
    else:
        raw_token = header.strip()

    if not raw_token:
        return None

    token_info = auth_service.verify_token(raw_token)   # raises on invalid
    if token_info.groups:
        return token_info.groups[0]          # primary group = first in list
    return None
```

This is a **pure function** that reads the ContextVar set by the middleware and returns a group string or `None`. All auth exceptions propagate to the caller.

---

### Step 3 — Wire Group into Session-Creating Tools

**File:** `app/mcp_server/mcp_server.py`

In `_handle_get_content`, add group resolution and pass it to both session-create paths.

At the **top** of `_handle_get_content` (after argument parsing, before any fetch):

```python
group = _resolve_token_group()
```

Then in both `create_session` call sites:

```python
# depth=1 session path (~L870)
session_id = manager.create_session(
    url=url, content=page_data, chunk_size=c_size, group=group,
)

# depth>1 session path (~L970)
session_id = manager.create_session(
    url=url, content=results, chunk_size=c_size, group=group,
)
```

**Effect:** Sessions are now tagged with the token's primary group. Anonymous requests (no token / auth disabled) create sessions with `group=None` (global).

---

### Step 4 — Wire Group into Session-Reading Tools

**File:** `app/mcp_server/mcp_server.py`

Add `group = _resolve_token_group()` at the top of each handler, then pass it through:

| Handler | Current Call | New Call |
|---------|-------------|----------|
| `_handle_get_session_info` | `manager.get_session_info(session_id)` | `manager.get_session_info(session_id, group=group)` |
| `_handle_get_session_chunk` | `manager.get_chunk(session_id, chunk_index)` | `manager.get_chunk(session_id, chunk_index, group=group)` |
| `_handle_list_sessions` | `manager.list_sessions()` | `manager.list_sessions(group=group)` |
| `_handle_get_session_urls` | `manager.get_session_info(session_id)` | `manager.get_session_info(session_id, group=group)` |

**Effect:** `SessionManager` enforces group match and raises `PermissionDeniedError` on mismatch. `list_sessions` returns only sessions owned by the caller's group.

---

### Step 5 — Map Auth and Permission Errors to MCP Responses

**File:** `app/errors/mapper.py`

Add entries for `AuthError` (401) and `PermissionDeniedError` (403) so they return structured MCP error responses instead of unhandled exceptions.

```python
from gofr_common.auth.exceptions import AuthError
from gofr_common.storage.exceptions import PermissionDeniedError

# In RECOVERY_STRATEGIES dict:
"AUTH_ERROR": "Check that a valid Bearer token is included in the Authorization header.",
"PERMISSION_DENIED": "Your token's groups do not include the group that owns this session.",
```

**File:** `app/mcp_server/mcp_server.py`

In each session handler's except chain, catch these new exception types:

```python
except AuthError as e:
    return _error_response(
        "AUTH_ERROR", str(e), recovery_strategy="Include a valid Bearer token."
    )
except PermissionDeniedError as e:
    return _error_response(
        "PERMISSION_DENIED", str(e),
        recovery_strategy="Use a token whose groups include the session's owner group."
    )
```

Alternatively, add a shared `_with_auth_errors` wrapper/decorator that catches these around any handler that calls `_resolve_token_group()`.

---

### Step 6 — Wire Group into Web Server Session Endpoints

**File:** `app/web_server/web_server.py`

The web server has `self.auth_service` but never uses it.

**6a.** Add auth middleware to the web server's Starlette app (same pattern as MCP — `include_auth_middleware=bool(auth_service)`).

**6b.** Add a `_resolve_group(self, request)` method:

```python
def _resolve_group(self, request) -> str | None:
    if self.auth_service is None:
        return None
    auth_header = request.headers.get("authorization", "")
    if not auth_header:
        return None
    raw = auth_header.removeprefix("Bearer ").strip()
    token_info = self.auth_service.verify_token(raw)
    return token_info.groups[0] if token_info.groups else None
```

**6c.** Call `group = self._resolve_group(request)` at the top of each session endpoint and pass `group=group` to all `SessionManager` calls.

**6d.** Catch `AuthError` → 401 JSON, `PermissionDeniedError` → 403 JSON.

---

### Step 7 — Handle Anonymous / No-Auth Mode

The design must be backwards-compatible:

| Scenario | `auth_service` | Middleware | `_resolve_token_group()` | Session group |
|----------|---------------|------------|--------------------------|---------------|
| `--no-auth` flag | `None` | Off | Returns `None` | `None` (global) |
| Auth enabled, no token sent | Set | On (no header captured) | Returns `None` | `None` (global) |
| Auth enabled, valid token | Set | On (header captured) | Returns `groups[0]` | `"myteam"` |
| Auth enabled, invalid token | Set | On (header captured) | Raises `AuthError` | — (401) |

**`group=None` sessions are world-readable.** This is intentional — anonymous sessions have no owner and can be read by anyone. Only group-owned sessions enforce access control.

---

### Step 8 — Tests

| Test | What it verifies |
|------|-----------------|
| **No token → session created with `group=None`** | Anonymous access still works |
| **Token with `groups=["team-a"]` → session tagged `"team-a"`** | Group extraction + create |
| **Token with `groups=["team-a"]` reads `"team-a"` session → 200** | Group match allows read |
| **Token with `groups=["team-b"]` reads `"team-a"` session → 403** | Group mismatch blocks read |
| **Token with `groups=["team-a", "team-b"]` reads `"team-a"` session → 200** | Any group in list works |
| **Invalid token → 401** | Auth error propagation |
| **`list_sessions` with `"team-a"` token → only `"team-a"` sessions** | Group-scoped listing |
| **`--no-auth` mode → all sessions accessible** | Backwards compatibility |
| **Web endpoint `/sessions/{id}/info` with wrong group → 403** | Web server enforcement |

---

## File Change Summary

| File | Changes |
|------|---------|
| `app/mcp_server/mcp_server.py` | Enable auth middleware, add `_resolve_token_group()`, pass `group` to all session ops, catch auth/permission errors |
| `app/web_server/web_server.py` | Add `_resolve_group()`, pass `group` to all session ops, add error handling |
| `app/errors/mapper.py` | Add `AUTH_ERROR` and `PERMISSION_DENIED` recovery strategies |
| `test/mcp/test_session_auth.py` | New test file for group-scoped session access |
| `test/web/test_session_auth.py` | New test file for web endpoint group enforcement |

**No changes needed to:**
- `gofr_common` (auth, middleware, storage — all already support this)
- `app/session/manager.py` (already accepts and enforces `group`)
- `app/main_mcp.py` / `app/main_web.py` (auth_service already created and injected)

---

## Execution Order

Steps 1-5 can be done as a single PR (MCP server). Step 6 can follow (web server). Step 7 is design validation (no code). Step 8 spans both.

**Estimated scope:** ~80 lines changed, ~150 lines of new tests.
