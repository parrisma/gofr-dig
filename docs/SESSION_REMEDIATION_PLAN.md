# Session Management Remediation Plan

## Context

Audit of the codebase against [SESSION_MANAGEMENT_PROPOSAL.md](SESSION_MANAGEMENT_PROPOSAL.md) found **6 gaps** between the proposal and the implementation. The core pattern (store → return GUID → retrieve by chunk) is correctly implemented. The gaps are around web endpoints, auth enforcement, missing features, and incomplete MCP integration.

---

## Gap Summary

| # | Gap | Severity | Proposal Section |
|---|-----|----------|------------------|
| 1 | Web routes differ; no full-download or streaming endpoint | HIGH | §4.3 |
| 2 | No auth on web session endpoints | **CRITICAL** | §3.3, §4.3 |
| 3 | `get_structure` doesn't support `session=true` | MEDIUM | §4.1 |
| 4 | No `preview` field in session response | LOW | §4.1 |
| 5 | No session housekeeping / expiry | MEDIUM | §3.2 |
| 6 | Group not passed from MCP tools to SessionManager | HIGH | §3.3 |

---

## Step-by-Step Remediation

### Step 1 — Add auth enforcement to web session endpoints

**Files:** `app/web_server/web_server.py`  
**Severity:** CRITICAL  
**Effort:** ~1 hour

The web server has `self.auth_service` available but the session endpoints never check it. Any unauthenticated request can read any session.

1. In `get_session_info`, extract the `Authorization: Bearer <token>` header.
2. Call `self.auth_service.verify_token(token)` to get the caller's group.
3. Pass the group to `self.session_manager.get_session_info(session_id, group=group)`.
4. Return 401 if no token or invalid token; 403 if group doesn't match.
5. Repeat for `get_session_chunk`.
6. If `self.auth_service` is `None` (no-auth mode), skip the check.

**Test (new):** `test/web/test_session_endpoints_auth.py`
- `test_session_info_returns_401_without_token`
- `test_session_info_returns_403_wrong_group`
- `test_session_info_returns_200_with_valid_token`
- `test_session_chunk_returns_401_without_token`

---

### Step 2 — Pass group from MCP tools to SessionManager

**Files:** `app/mcp_server/mcp_server.py`  
**Severity:** HIGH  
**Effort:** ~1 hour

The MCP handlers `_handle_get_session_info` and `_handle_get_session_chunk` never extract a group from the request context, so the ACL in `SessionManager` is never exercised.

1. Determine how to get the caller's group from the MCP request context.
   - If auth middleware populates a context variable (e.g., `request.state.group`), use it.
   - If not, accept an optional `group` parameter on the tool schema (less secure but functional).
2. In `_handle_get_content` where `manager.create_session(...)` is called (~line 732), pass the caller's group so the session is owned.
3. In `_handle_get_session_info` (~line 961), pass `group` to `manager.get_session_info()`.
4. In `_handle_get_session_chunk` (~line 975), pass `group` to `manager.get_chunk()`.

**Test (new):** `test/mcp/test_session_acl.py`
- `test_create_session_stores_group`
- `test_get_session_info_denied_wrong_group`
- `test_get_session_chunk_denied_wrong_group`

---

### Step 3 — Add full-download endpoint (`GET /sessions/{id}`)

**Files:** `app/web_server/web_server.py`  
**Severity:** HIGH  
**Effort:** ~1 hour

The proposal specifies `GET /session/{session_id}` to download the full JSON result. The current code only has `/sessions/{id}/info` (metadata) and `/sessions/{id}/chunks/{idx}` (single chunk). There is no way to download the complete content via web.

1. Add a new route: `Route("/sessions/{session_id}", endpoint=self.get_session_full, methods=["GET"])`.
2. Implement `get_session_full`:
   - Auth check (same as Step 1).
   - Call `self.session_manager.storage.get(session_id, group=group)`.
   - Return the raw JSON blob as `application/json` response.
3. Set `Content-Disposition: attachment; filename="{session_id}.json"` header for download friendliness.

**Test (new):** `test/web/test_session_download.py`
- `test_download_full_session_returns_json`
- `test_download_nonexistent_session_returns_404`
- `test_download_requires_auth`

---

### Step 4 — Add streaming endpoint (`GET /sessions/{id}/stream`)

**Files:** `app/web_server/web_server.py`  
**Severity:** MEDIUM (nice-to-have per proposal)  
**Effort:** ~2 hours

The proposal specifies a streaming endpoint for very large datasets.

1. Add route: `Route("/sessions/{session_id}/stream", endpoint=self.stream_session, methods=["GET"])`.
2. Implement `stream_session`:
   - Auth check.
   - Use Starlette's `StreamingResponse`.
   - Iterate over chunks using `session_manager.get_chunk(id, i)` for `i` in `range(total_chunks)`.
   - Yield each chunk as a newline-delimited JSON fragment or plain text segment.
3. Set `Content-Type: text/plain; charset=utf-8` or `application/x-ndjson` depending on format.

**Test (new):** `test/web/test_session_stream.py`
- `test_stream_returns_all_chunks`
- `test_stream_large_session`

---

### Step 5 — Add `session=true` support to `get_structure`

**Files:** `app/mcp_server/mcp_server.py`  
**Severity:** MEDIUM  
**Effort:** ~1 hour

The proposal says `get_content`, `get_structure`, and `crawl` all accept the `session` parameter. Only `get_content` does today.

1. Add `session` (boolean) and `chunk_size` (integer) properties to the `get_structure` tool schema.
2. In `_handle_get_structure` (around line 900), after building the structure response dict:
   - If `session=true`, call `manager.create_session(content=response, url=url, chunk_size=...)`.
   - Return session metadata instead of the full structure.
3. Follow the same pattern as `_handle_get_content`'s session logic.

**Test (new):** `test/mcp/test_get_structure_session.py`
- `test_get_structure_session_returns_session_id`
- `test_get_structure_session_chunk_retrieval`

---

### Step 6 — Add `preview` field to session response

**Files:** `app/mcp_server/mcp_server.py`  
**Severity:** LOW  
**Effort:** ~30 minutes

The proposal shows a `preview` field with a text snippet in the session creation response. This helps the LLM decide whether to fetch chunks.

1. In `_handle_get_content`, after creating the session (~line 732):
   - Read chunk 0 from the manager.
   - Truncate to ~500 chars.
   - Add as `"preview": truncated_text` in the response dict.
2. Also add `preview` to the `get_session_info` response in `SessionManager.get_session_info()`.

**Test (update):** `test/mcp/test_session_tools.py` (or new)
- `test_session_response_includes_preview`
- `test_preview_is_truncated`

---

### Step 7 — Add session housekeeping / expiry

**Files:** `app/session/manager.py`  
**Severity:** MEDIUM  
**Effort:** ~2 hours

Without cleanup, the `data/sessions/` directory grows indefinitely.

1. Add a `max_age_seconds` parameter to `SessionManager.__init__` (default: 86400 = 24h).
2. Add method `cleanup_expired()`:
   - Iterate metadata entries.
   - Delete sessions where `now - created_at > max_age_seconds`.
   - Return count of deleted sessions.
3. Call `cleanup_expired()` lazily on `create_session()` (at most once per hour, tracked by an instance timestamp).
4. Optionally, add a `cleanup_sessions` MCP tool for manual invocation.

**Test (new):** `test/session/test_session_expiry.py`
- `test_expired_session_cleaned_up`
- `test_unexpired_session_preserved`
- `test_cleanup_rate_limited`
- `test_cleanup_returns_count`

---

## Execution Order

```
Step 1  Auth on web endpoints           ██████████  CRITICAL   ~1h
Step 2  Group in MCP tools              ██████████  HIGH       ~1h
Step 3  Full download endpoint          ████████    HIGH       ~1h
Step 4  Streaming endpoint              ██████      MEDIUM     ~2h
Step 5  get_structure session support   ██████      MEDIUM     ~1h
Step 6  Preview field                   ████        LOW        ~30m
Step 7  Session expiry                  ██████      MEDIUM     ~2h
                                                    ─────────────
                                        Total:      ~8.5 hours
                                        New tests:  ~20
```

Steps 1–2 should be done first (security). Steps 3–7 are independent and can be done in any order.

---

## Files Affected

| File | Steps |
|------|-------|
| `app/web_server/web_server.py` | 1, 3, 4 |
| `app/mcp_server/mcp_server.py` | 2, 5, 6 |
| `app/session/manager.py` | 6, 7 |

## New Test Files

| File | Steps |
|------|-------|
| `test/web/test_session_endpoints_auth.py` | 1 |
| `test/web/test_session_download.py` | 3 |
| `test/web/test_session_stream.py` | 4 |
| `test/mcp/test_session_acl.py` | 2 |
| `test/mcp/test_get_structure_session.py` | 5 |
| `test/mcp/test_session_preview.py` | 6 |
| `test/session/test_session_expiry.py` | 7 |

---

## Document History

| Date | Version | Changes |
|------|---------|---------|
| 2026-02-08 | 1.0 | Initial plan from proposal-vs-code audit |
