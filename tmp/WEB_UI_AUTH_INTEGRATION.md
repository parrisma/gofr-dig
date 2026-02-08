# Web UI — Auth Integration Guide

Instructions for the web UI to align with the gofr-dig group-based session auth model.

---

## TL;DR

gofr-dig now enforces **group-scoped session access**. Every session is owned by a group. The web UI must:

1. **Obtain a JWT** from the auth service.
2. **Send it as `Authorization: Bearer <jwt>`** on every REST call to `/sessions/*`.
3. **Pass it as `auth_tokens: ["<jwt>"]`** on every MCP tool call.
4. **Handle 401 and 403** error responses gracefully.

---

## 1. Token Format

Tokens are HS256 JWTs issued by `gofr_common.auth.AuthService`. The payload contains:

```json
{
  "sub": "<token-id>",
  "groups": ["team-a", "team-b"],
  "exp": 1738972800,
  "iat": 1738886400
}
```

**Key field:** `groups` — an ordered list of group names. The **first group** (`groups[0]`) is the "primary group" used to tag new sessions.

---

## 2. Two Auth Delivery Paths

The backend accepts auth via two mechanisms depending on the call type:

### A. Web REST Endpoints (direct HTTP)

Send as a standard HTTP header:

```
Authorization: Bearer <jwt>
```

**Applies to:**

| Endpoint | Method | Auth header? |
|----------|--------|-------------|
| `GET /sessions/{id}/info` | GET | Yes |
| `GET /sessions/{id}/chunks/{index}` | GET | Yes |
| `GET /sessions/{id}/urls` | GET | Yes |
| `GET /ping` | GET | No (public) |
| `GET /health` | GET | No (public) |

### B. MCP Tool Calls (via MCPO proxy)

HTTP headers are **not** reliably forwarded through the MCPO proxy to individual tool invocations. Instead, pass tokens as a **tool parameter**:

```json
{
  "url": "https://example.com",
  "session": true,
  "auth_tokens": ["<jwt>"]
}
```

**`auth_tokens`** is accepted by every tool except `ping`. It is an array of JWT strings. The server tries each token in order and uses the first valid one.

---

## 3. Permission Model

```
CREATE session:  token.groups[0]  →  session.group = "team-a"
READ session:    if requesting_group == session.group  →  200 OK
                 if requesting_group != session.group  →  403 PERMISSION_DENIED
                 if no token / auth disabled           →  group=None (public only)
```

- **Sessions created without a token** have `group = null` (public).
- **Public sessions** (`group = null`) are readable by everyone.
- **Group-scoped sessions** are only readable by tokens that carry that group.
- **list_sessions** returns only sessions matching the token's group (plus public sessions when `group = null`).

---

## 4. Error Responses

The web UI must handle these error shapes:

### 401 — AUTH_ERROR (invalid/expired/revoked token)

```json
{
  "error": {
    "code": "AUTH_ERROR",
    "message": "Token expired"
  }
}
```

**UI action:** Prompt re-authentication. Clear stored token. Redirect to login.

### 403 — PERMISSION_DENIED (valid token, wrong group)

```json
{
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "Access denied to session abc123"
  }
}
```

**UI action:** Show "Access Denied" message. Do **not** prompt re-login (the token is valid, just wrong group). Offer to switch group if multi-group token.

### MCP Tool Error (same codes, different envelope)

MCP tool calls return errors in the standard MCP response format:

```json
{
  "success": false,
  "error_code": "AUTH_ERROR",
  "error": "Token expired",
  "recovery": "Re-authenticate and retry with a valid token."
}
```

```json
{
  "success": false,
  "error_code": "PERMISSION_DENIED",
  "error": "Access denied to session abc123",
  "recovery": "Verify that your token includes the required group."
}
```

---

## 5. What the Web UI Needs to Implement

### 5.1 Token Storage

The UI already stores JWTs against logical names. No new storage mechanism is needed — just use the existing named-token store.

When making requests to gofr-dig, resolve the appropriate named token and attach it as described below. If no token is configured for the gofr-dig service, omit auth entirely (anonymous/public mode).

### 5.2 Request Interceptor

Add an interceptor/middleware to outgoing HTTP requests:

```typescript
// Pseudocode
function addAuth(request: Request): Request {
  const token = getStoredToken();
  if (token) {
    request.headers["Authorization"] = `Bearer ${token}`;
  }
  return request;
}
```

### 5.3 MCP Tool Call Wrapper

When calling MCP tools (via MCPO or direct), inject `auth_tokens`:

```typescript
// Pseudocode
function callTool(name: string, args: Record<string, any>) {
  const token = getStoredToken();
  if (token) {
    args.auth_tokens = [token];
  }
  return mcpClient.callTool(name, args);
}
```

### 5.4 Error Handling

```typescript
// Pseudocode
async function handleResponse(response: Response) {
  if (response.status === 401) {
    clearToken();
    redirectToLogin();
    return;
  }
  if (response.status === 403) {
    showAccessDenied("You don't have permission to view this session.");
    return;
  }
  // ... handle 404, 400, 500 as before
}
```

For MCP responses, check `error_code`:

```typescript
function handleMCPResult(result: any) {
  if (result.success === false) {
    if (result.error_code === "AUTH_ERROR") {
      clearToken();
      redirectToLogin();
      return;
    }
    if (result.error_code === "PERMISSION_DENIED") {
      showAccessDenied(result.recovery || result.error);
      return;
    }
    // ... other error codes
  }
}
```

### 5.5 Anonymous Mode

When no token is stored (user not logged in):

- **Omit** the `Authorization` header and `auth_tokens` parameter entirely.
- The backend treats this as anonymous (`group = null`).
- Only public/unowned sessions will be visible and accessible.
- The UI should still work — just with limited session visibility.

### 5.6 Multi-Group Tokens

A token can carry multiple groups: `groups: ["team-a", "team-b"]`.

- `groups[0]` is always used as the "primary group" for **creating** sessions.
- For **reading**, the backend checks if the session's group matches the token's primary group.
- If the UI needs to create sessions under different groups, it needs separate tokens (one per group) or the backend would need a `target_group` parameter (not yet implemented).

---

## 6. Service URLs

| Service | Default Port | Env Var |
|---------|-------------|---------|
| MCP (Streamable HTTP) | 8070 | `GOFR_DIG_MCP_PORT` |
| MCPO (OpenAPI proxy) | 8071 | `GOFR_DIG_MCPO_PORT` |
| Web REST | 8072 | `GOFR_DIG_WEB_PORT` |

In Docker dev: use container service names (`mcp:8070`, `mcpo:8071`, `web:8072`).
In production: use published host ports or configured URLs.

---

## 7. Quick Reference — Request Examples

### Create a session (MCP tool via MCPO)

```bash
curl -X POST http://localhost:8071/get_content \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "session": true,
    "auth_tokens": ["eyJhbGciOi..."]
  }'
```

### Read session info (Web REST)

```bash
curl http://localhost:8072/sessions/abc123/info \
  -H "Authorization: Bearer eyJhbGciOi..."
```

### Read a chunk (Web REST)

```bash
curl http://localhost:8072/sessions/abc123/chunks/0 \
  -H "Authorization: Bearer eyJhbGciOi..."
```

### List sessions (MCP tool via MCPO)

```bash
curl -X POST http://localhost:8071/list_sessions \
  -H "Content-Type: application/json" \
  -d '{"auth_tokens": ["eyJhbGciOi..."]}'
```

### Get chunk URLs (MCP tool)

```bash
curl -X POST http://localhost:8071/get_session_urls \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123",
    "auth_tokens": ["eyJhbGciOi..."]
  }'
```

---

## 8. Summary of Changes from Previous (No-Auth) Behavior

| Before | After |
|--------|-------|
| All sessions visible to everyone | Sessions scoped by group |
| No auth headers needed | `Authorization: Bearer` required for group-scoped access |
| MCP tools had no auth param | All tools (except ping) accept `auth_tokens` array |
| Errors: 404, 400, 500 only | New: 401 (`AUTH_ERROR`), 403 (`PERMISSION_DENIED`) |
| No token management needed | UI must store, send, and refresh JWT tokens |

**Backwards compatible:** If no token is sent, behavior is identical to before (anonymous/public access). Existing integrations won't break — they just won't see group-scoped sessions.
