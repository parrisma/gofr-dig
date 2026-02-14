# Tools Spec Implementation Plan

This plan implements the accepted usability/security changes from the tool-spec review.

## Scope

In scope:

1. Align runtime behavior with updated `docs/tools.md`.
2. Complete partially-applied changes (`auth_token`, SSRF, rate limit, char limits).
3. Add missing behavior: `timeout_seconds`, `get_structure.selector` execution path.
4. Update tests and docs impacted by API contract changes.

Out of scope:

- Pagination for `list_sessions`.
- New housekeeping tool.
- API versioning.

## Execution Steps

### Step 1 — Stabilize current MCP contracts

- Ensure all tool schemas consistently use `auth_token` (string).
- Remove any stale `auth_tokens` references in runtime and errors.
- Confirm `set_antidetection` exposes `max_response_chars` and no toggle for robots.

Status: ✅ complete (already applied; verify via tests in later steps).

### Step 2 — Complete `get_structure.selector` implementation

- Add optional `selector` parameter to structure analysis execution path (not just schema).
- Update `StructureAnalyzer.analyze()` to support scoping analysis to a selected subtree.
- Preserve behavior when selector is omitted.

Status: ✅ complete.

### Step 3 — Add per-request timeout control

- Add `timeout_seconds` argument support to `get_content` and `get_structure`.
- Thread timeout into fetch path so each call can override default timeout.
- Enforce sane bounds and return `INVALID_ARGUMENT` on invalid values.
- Keep default timeout at 60 seconds.

Status: ✅ complete.

### Step 4 — Harden/align error mapping text

- Update recovery text for auth and robots messaging to match new contract.
- Ensure `RATE_LIMIT_EXCEEDED`, `SSRF_BLOCKED`, and `INVALID_MAX_RESPONSE_CHARS` are documented and surfaced consistently.

Status: ✅ complete.

### Step 5 — Update tests for contract changes

- Update MCP schema tests for:
  - `auth_token` (not `auth_tokens`)
  - `max_response_chars` (not `max_tokens`)
  - no configurable `respect_robots_txt`
  - `selector` and `timeout_seconds` presence where expected
- Update behavior tests for:
  - response type discriminator (`inline`/`session`)
  - SSRF block path
  - inbound rate limit response

Status: ✅ complete.

### Step 6 — Run validation test suites

- Run targeted tests first for touched modules.
- Then run full test suite via `./scripts/run_tests.sh` per project requirement.
- Capture failures and fix only issues caused by this change set.

Status: ✅ complete — 438/438 passing.

### Step 7 — Final documentation consistency pass

- Verify examples and field names in docs match code.
- Ensure `base_url` fragility and chunk-size guidance remain accurate.

Status: ✅ complete — docs/tools.md fully aligned with code.

## Live Progress Tracker

- [x] Step 1 — Stabilize current MCP contracts
- [x] Step 2 — Complete `get_structure.selector` implementation
- [x] Step 3 — Add per-request timeout control
- [x] Step 4 — Harden/align error mapping text
- [x] Step 5 — Update tests for contract changes
- [x] Step 6 — Run validation test suites
- [x] Step 7 — Final documentation consistency pass
