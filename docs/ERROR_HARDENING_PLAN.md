# Error Hardening Plan

Systematic plan to ensure every error represents the real failure and includes a recovery strategy.

## Audit Summary

A full audit found **11 critical/moderate gaps** in the error handling across the codebase. The problems group into four themes:

| Theme | Impact | Items |
|---|---|---|
| **A. Wrong exception types** | Errors lose semantic meaning, wrong HTTP status codes | 3 |
| **B. Dead/unused error infrastructure** | Wasted code, inconsistent paths | 3 |
| **C. Missing error codes + recovery strategies** | Generic "try again" messages instead of actionable guidance | 5 |
| **D. Silent failures / missing logs** | Errors vanish — invisible to operators | 5 |

---

## Phase 1 — Fix Exception Types in SessionManager ✅ DONE

**Status:** Completed 2026-02-08

**Files changed:**
- `app/exceptions/session.py` — **Created.** Real exception module replacing dynamic stubs. Defines `SessionError`, `SessionNotFoundError`, `SessionValidationError`, `InvalidSessionStateError`.
- `app/session/manager.py` — Replaced 3 `raise ValueError(...)` with typed exceptions using `(code, message, details)` constructor:
  - `SessionNotFoundError("SESSION_NOT_FOUND", ...)` with `{"session_id": ...}` details
  - `SessionValidationError("INVALID_CHUNK_INDEX", ...)` with `{"chunk_index": ..., "total_chunks": ...}` details
- `test/session/test_session_manager.py` — Updated 2 assertions from `pytest.raises(ValueError)` to `pytest.raises(SessionNotFoundError)` / `pytest.raises(SessionValidationError)`

**Result:** 301 tests pass (including pyright type checks). Session errors now carry machine-readable codes and structured details.

---

## Phase 2 — Use Typed Exceptions in MCP Tool Handlers ✅ DONE

**Status:** Completed 2026-02-08

**Files changed:**
- `app/mcp_server/mcp_server.py`:
  - Fixed module docstring (removed "Hello World Implementation")
  - All 4 session handler `except` blocks now catch `GofrDigError` first → routes through `_exception_response()` (which uses the error mapper for structured codes + recovery strategies), then `Exception` as fallback with `logger.error()` context
  - Handlers updated: `_handle_get_session_info`, `_handle_get_session_chunk`, `_handle_list_sessions`, `_handle_get_content` (session creation block)

**Result:** `_exception_response()` is no longer dead code. `SessionNotFoundError` → `RESOURCE_NOT_FOUND` with mapper recovery. `SessionValidationError` → `SESSION_VALIDATION` with mapper recovery. Unexpected errors get explicit `logger.error()` with context fields.

---

## Phase 3 — Add Missing Recovery Strategies ✅ DONE

**Status:** Completed 2026-02-08

**Files changed:**
- `app/errors/mapper.py` — Added 5 missing `RECOVERY_STRATEGIES` entries:
  - `INVALID_ARGUMENT` — "A required argument is missing or invalid..."
  - `INVALID_MAX_TOKENS` — "max_tokens must be between 1000 and 1000000..."
  - `SESSION_ERROR` — "Session operation failed. Use list_sessions..."
  - `SESSION_NOT_FOUND` — "Session ID not found. Use list_sessions to discover sessions..."
  - `INVALID_CHUNK_INDEX` — "Chunk index out of range. Use get_session_info..."

**Result:** Every error code used in `_error_response` calls now has an actionable recovery strategy. No more generic "Review the error message and try again." fallbacks for session/argument errors.

---

## Phase 4 — Differentiate Fetch Error Codes ✅ DONE

**Status:** Completed 2026-02-08

**Files changed:**
- `app/mcp_server/mcp_server.py`:
  - Added `FetchResult` import from `app.scraping`
  - Added `_classify_fetch_error(result: FetchResult) -> str` helper that maps HTTP status codes and error strings to specific codes: `URL_NOT_FOUND` (404), `ACCESS_DENIED` (403), `RATE_LIMITED` (429 or `rate_limited` flag), `TIMEOUT_ERROR` (timeout/timed out in error), `CONNECTION_ERROR` (connect/resolve/dns in error), `FETCH_ERROR` (fallback for 5xx and others)
  - `fetch_single_page`: Replaced 15-line inline `if/elif` block with 6-line classifier call. Now returns `error_code` and `recovery_strategy` from `RECOVERY_STRATEGIES` for every fetch failure
  - `_handle_get_structure`: Replaced hardcoded `"FETCH_ERROR"` with `_classify_fetch_error(fetch_result)` so 404s → `URL_NOT_FOUND`, 403s → `ACCESS_DENIED`, etc.
- `test/mcp/test_get_content.py` — Updated `test_get_content_404`: added `error_code == "URL_NOT_FOUND"` assertion
- `test/mcp/test_get_structure.py` — Updated `test_get_structure_404`: changed assertion from `FETCH_ERROR` → `URL_NOT_FOUND`

**Result:** 11 of 19 previously-unused `RECOVERY_STRATEGIES` codes are now reachable from fetch paths. Every HTTP error class (404, 403, 429, 5xx, timeout, DNS) gets a specific error code with tailored recovery guidance. 227 tests pass.

---

## Phase 5 — Differentiate Extraction Error Codes ✅ DONE

**Status:** Completed 2026-02-08

**Files changed:**
- `app/mcp_server/mcp_server.py`:
  - Added `_classify_extraction_error(error_msg: str) -> str` helper that maps extractor error strings to specific codes: `SELECTOR_NOT_FOUND` ("did not match" + "selector"), `INVALID_SELECTOR` ("invalid selector"), `ENCODING_ERROR` ("encoding"/"decode"), `EXTRACTION_ERROR` (fallback)
  - `fetch_single_page`: Replaced bare `{"success": False, "error": content.error}` with classified response including `error_code` and `recovery_strategy` from `RECOVERY_STRATEGIES`

**Result:** Content extraction failures now carry specific error codes with tailored recovery guidance (e.g., "The CSS selector matched no elements. Verify the selector syntax…"). 119 targeted tests pass (55 core + 64 fixture-dependent).

---

## Phase 6 — Harden Web Server Error Handling ✅ DONE

**Status:** Completed 2026-02-08

**Files changed:**
- `app/web_server/web_server.py`:
  - Added imports: `GofrDigError`, `SessionNotFoundError`, `SessionValidationError`, `error_to_web_response`, `logger`
  - `get_session_info`: Now catches `SessionNotFoundError` → 404 with `error_to_web_response()`, `GofrDigError` → 400, `Exception` → 500 with `INTERNAL_ERROR` code. All paths log with structured fields.
  - `get_session_chunk`: Now catches `SessionNotFoundError` → 404, `SessionValidationError` → 400 (was 404), `GofrDigError` → 400, `Exception` → 500. All paths log with structured fields.
  - `error_to_web_response()` is no longer dead code — both handlers use it for typed exceptions.
- `test/web/test_session_endpoints.py`:
  - Updated to use `SessionNotFoundError`/`SessionValidationError` instead of `ValueError`
  - Added `test_get_session_chunk_invalid_index` — verifies bad chunk index returns 400 (not 404) with `SESSION_VALIDATION` error code
  - Assertions now check structured `data["error"]["code"]` instead of bare `data["detail"]`

**Result:** Web server now returns structured error responses with error codes and recovery strategies via the same mapper used by MCP handlers. Bad chunk index correctly returns 400 (previously 404). 10 tests pass (5 web + 5 code quality).

---

## Phase 7 — Add Logging to Silent Exception Handlers ✅ DONE

**Status:** Completed 2026-02-08

**Files changed:**
- `app/scraping/extractor.py`:
  - `extract_by_selector`: Added `logger.error("Failed to parse HTML for selector extraction", ...)` to parse failure + `logger.warning("Invalid CSS selector", selector=..., error=...)` to selector failure. Both were previously silent.
  - `extract_main_content`: Added `logger.error("Failed to parse HTML for main content extraction", error=..., url=...)` to parse failure (was silent).
- `app/management/storage_manager.py`:
  - Added `from app.logger import session_logger as logger`
  - Added `logger.error(...)` with structured fields before each of 3 `print(f"Error ...")` calls: `purge` (L78), `list_items` (L123), `stats` (L162). CLI `print()` retained for user output.
- `app/main_mcpo.py`:
  - Changed `logger.error("Failed to start MCPO wrapper")` to include structured context: `reason="wrapper process not created"`, `host=args.mcpo_host`, `port=args.mcpo_port`.

**Result:** All exception handlers now log with structured fields. No more silent failures — operators can see parse errors, storage errors, and startup failures in logs. 102 targeted tests pass.

---

## Phase 8 — Validate with Tests ✅ DONE

**Status:** Completed 2026-02-08

**Files created:**
- `test/errors/test_error_hardening.py` — 55 tests across 7 test classes:
  1. **TestSessionManagerExceptions** (3 tests): Verifies `SessionNotFoundError` with correct `.code` and `.details`, `SessionValidationError` for bad chunk index
  2. **TestClassifyFetchError** (11 tests): Every branch of `_classify_fetch_error` — 404→URL_NOT_FOUND, 403→ACCESS_DENIED, 429→RATE_LIMITED, rate_limited flag, 500/502→FETCH_ERROR, timeout/timed out→TIMEOUT_ERROR, connect/resolve/dns→CONNECTION_ERROR, unknown→FETCH_ERROR
  3. **TestClassifyExtractionError** (6 tests): Every branch of `_classify_extraction_error` — selector not found, invalid selector, encoding, decode, generic, empty string
  4. **TestMCPToolErrorCodes** (5 tests): Mocked session manager returning typed exceptions, unknown tool, missing URL for get_content/get_structure
  5. **TestErrorResponseStructure** (27 tests): Parametrized over all 25 RECOVERY_STRATEGIES keys to verify each produces a correct recovery_strategy; plus fallback and details tests
  6. **TestErrorMapperResponses** (2 tests): Verifies `error_to_mcp_response` and `error_to_web_response` return required fields
  7. **TestRecoveryStrategiesCoverage** (2 tests): Audit that every RECOVERY_STRATEGIES key is either reachable or documented as known-unlinked; every emitted code has a strategy

**Result:** 55 new tests all pass. Locks in all hardening from Phases 1–7.

---

## Phase 9 — Cleanup Dead Code

1. **Remove orphan RECOVERY_STRATEGIES** that can never be emitted after Phase 4/5 (should be none — all should now be reachable).
2. **Remove `INVALID_HEADERS` recovery strategy** if we decide not to validate custom headers (currently no validation exists).
3. **Update the module docstring** at top of `mcp_server.py` — still says "Hello World Implementation".

---

## Execution Order

| Phase | Scope | Risk | Est. Effort |
|---|---|---|---|
| 1 | SessionManager exceptions | Low | 10 min |
| 2 | MCP handler exception dispatch | Low | 15 min |
| 3 | Add missing recovery strategies | None | 5 min |
| 4 | Fetch error classification | Medium | 20 min |
| 5 | Extraction error classification | Low | 10 min |
| 6 | Web server hardening | Low | 15 min |
| 7 | Add missing logging | None | 10 min |
| 8 | Validation tests | None | 30 min |
| 9 | Dead code cleanup | None | 5 min |

**Total: ~2 hours**

Phases 1–3 are safe and have immediate impact. Phase 4 is the most impactful change (fetch error differentiation). Phase 8 (tests) locks everything in.
