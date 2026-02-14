# SEQ Logging Reliability Migration Plan (Phased, Minimal Refactor)

Goal: move from in-process custom SEQ transport logic to a simpler, more reliable model where services emit structured logs locally and a dedicated shipper delivers to SEQ.

Scope: minimal change to business code paths (`app/mcp_server`, scraping/session logic) and no large refactor.

---

## Success Criteria

- [ ] No loss of MCP tool invocation/completion logs during normal operation.
- [ ] Logging continues if SEQ is unavailable.
- [ ] SEQ delivery recovers automatically when SEQ returns.
- [ ] Existing structured fields remain queryable (`event`, `tool`, `operation`, `stage`, `build_number`, etc.).
- [ ] All tests pass via `./scripts/run_tests.sh`.

---

## Phase 0 — Stabilize Current Path (Immediate Safety)

Objective: reduce immediate risk before migration.

Status: in progress (core implementation + unit coverage complete on 2026-02-14).

### Implementation

- [x] Keep current `SeqHandler` hotfix in place (thread restart + no `atexit` shutdown coupling).
- [x] Add internal health counters to `SeqHandler`:
  - [x] `events_enqueued`
  - [x] `events_dropped_queue_full`
  - [x] `post_failures`
  - [x] `last_post_error`
  - [x] `last_success_utc`
- [x] Emit rate-limited warning on drops/failures (e.g., once per 60s).

### Tests

- [x] Unit: queue full increments `events_dropped_queue_full`.
- [x] Unit: network error increments `post_failures` and records `last_post_error`.
- [x] Unit: successful post updates `last_success_utc`.
- [x] Integration: `ping` and `get_content` still produce logs in stdout/file.

### Exit Criteria

- [x] We can prove whether losses happen (observable counters, not silent failure).

---

## Phase 1 — Add Local Durable Log File as Source of Truth

Objective: ensure app logging is reliable independent of SEQ.

### Implementation

- [x] Confirm JSON file logging enabled for MCP and Web services via `GOFR_DIG_LOG_FILE` and `GOFR_DIG_LOG_JSON=true`.
  - **Note:** MCPO is a third-party proxy (`mcpo` binary) that does not use our StructuredLogger. Removed unused `LOG_FILE`/`LOG_JSON`/`SEQ` env vars from MCPO compose config. MCPO stdout/stderr captured by Docker log driver.
- [x] Standardize log line format to single-line JSON per event (validated via `json.loads` on live log lines).
- [x] Confirm volume mapping persists logs (`gofr-dig-prod-logs` shared across all 3 containers; verified consistent view).

### Tests

- [x] Integration: invoke `ping` via MCPO → MCP; verified MCP log grew from 405 to 449 lines with valid JSON events.
- [ ] Integration: restart service container; verify file path persists and new logs append (deferred — volume is Docker-managed, non-external; data persists unless `docker volume rm`).
- [x] Regression: 394 unit tests passed; 9 skipped (Vault-dependent, require full test env). No regressions from Phase 1 changes.

### Exit Criteria

- [x] Local durable logs are complete and queryable even with SEQ down.

---

## Phase 2 — Introduce Dedicated Log Shipper (Sidecar Pattern)

Objective: move transport/retry complexity out of application process.

### Implementation

- [ ] Add a lightweight shipper service in `docker/compose.prod.yml` (single responsibility: tail JSON logs and forward to SEQ).
- [ ] Mount `gofr-dig-prod-logs` read-only into shipper.
- [ ] Configure shipper with:
  - [ ] bounded memory/disk buffer
  - [ ] retry with backoff
  - [ ] delivery metrics (sent/failed/retried)
- [ ] Route to `GOFR_DIG_SEQ_URL` + API key from existing secret flow.
- [ ] Keep app SEQ direct sink enabled initially (temporary dual-write for validation window).

### Tests

- [ ] Integration: generate tool calls; confirm events arrive in SEQ with expected fields.
- [ ] Failure test: stop SEQ for 5–10 min; generate logs; restart SEQ; confirm buffered events are delivered.
- [ ] Failure test: restart shipper during load; confirm no process crash and continued delivery.

### Exit Criteria

- [ ] Shipper demonstrates reliable catch-up after SEQ outage.

---

## Phase 3 — Cut Over (Disable In-App SEQ Transport)

Objective: simplify app code and reduce failure surface.

### Implementation

- [ ] Add feature flag: `GOFR_DIG_SEQ_DIRECT_ENABLED` (default `false` in prod after cutover).
- [ ] When disabled, `StructuredLogger` does not attach `SeqHandler`.
- [ ] Keep stdout + file handlers unchanged.
- [ ] Keep startup log event `logging_sink_initialized`, but report sink as `shipper` in prod.

### Tests

- [ ] Unit: logger init does not create `SeqHandler` when direct disabled.
- [ ] Integration: MCP calls still logged locally and visible in SEQ via shipper.
- [ ] Regression: no change in application behavior or MCP responses.

### Exit Criteria

- [ ] No app-owned network thread for SEQ transport in prod.

---

## Phase 4 — Remove/Minimize Legacy SEQ Handler Code

Objective: reduce maintenance burden.

### Implementation

- [ ] Keep `SeqHandler` only for non-prod fallback (optional), or remove fully if no longer used.
- [ ] Remove dead config branches and obsolete comments.
- [ ] Update docs:
  - [ ] `docs/logging_vault_integration_guide.md`
  - [ ] runbook troubleshooting section (shipper health + backlog checks)

### Tests

- [ ] Full suite via `./scripts/run_tests.sh`.
- [ ] Smoke in prod-like compose stack.

### Exit Criteria

- [ ] Simpler logging architecture documented and validated.

---

## Rollout Strategy (Low Risk)

1. **Week 1:** Phase 0 + 1 (observability + durable local logs).
2. **Week 2:** Phase 2 dual-write (direct + shipper).
3. **Week 3:** Phase 3 cutover to shipper-only in prod.
4. **Week 4:** Phase 4 cleanup.

---

## Rollback Plan

- [ ] Keep `GOFR_DIG_SEQ_DIRECT_ENABLED=true` available for emergency re-enable.
- [ ] If shipper fails, continue local file logging and re-enable direct SEQ sink temporarily.
- [ ] Use local log files as recovery source for replay.

---

## Operational Checks After Each Deploy

- [ ] `docker logs gofr-dig-mcp` contains tool events (`tool_invoked`, `tool_completed`).
- [ ] Service log files in volume are growing.
- [ ] SEQ shows new events with `build_number` and tool fields.
- [ ] No sustained drop/failure counters (Phase 0 instrumentation).
