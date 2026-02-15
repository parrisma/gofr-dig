# Storage Manager SEQ Logging Spec

## Goal
Ensure storage manager operational events are consistently emitted through the core structured logging pipeline so they are visible in SEQ with actionable context.

This spec defines WHAT and WHY only (no code).

## Current State
1. `app/management/storage_manager.py` already imports `session_logger` from `app.logger`, which is backed by `gofr_common` structured logging.
2. The module currently mixes structured logger calls with direct `print()` output.
3. Some operator-relevant events are only visible in stdout and not guaranteed to be present as structured SEQ events.
4. The shell wrapper `scripts/storage_manager.sh` invokes the module with environment settings but does not produce startup/shutdown structured events itself.

## Problems to Solve
1. Incomplete observability: important outcomes (checks, skips, summaries, user-facing validation failures) may not have consistent structured events.
2. Event inconsistency: mixed naming/fields can make dashboards and alerts brittle.
3. Operational traceability: command invocation context is not emitted uniformly as structured fields.

## In Scope
1. Upgrade `app/management/storage_manager.py` to emit structured logs for command lifecycle:
   - command start
   - validation failures
   - prune/list/stats/purge summary
   - lock contention/stale lock handling
   - exception paths
2. Preserve current CLI usability (human-readable terminal output still acceptable), but ensure equivalent structured events are always logged.
3. Add/update tests verifying key structured events are produced.
4. Update docs to describe SEQ visibility for storage manager operations.

## Out of Scope
1. Replacing all terminal output in scripts with logging-only UX.
2. Broad logging refactor across unrelated modules.
3. Changes to SEQ transport internals in `gofr_common`.

## Functional Requirements
1. Every command (`purge`, `prune-size`, `list`, `stats`) emits a structured start and end event.
2. Validation failures emit structured warning/error events with cause and recovery context.
3. Prune operations include structured counters (item_count, deleted_count, freed_mb, final_mb, anomalies, lock status).
4. Non-zero exits must always have a structured error/warn event.

## Non-Functional Requirements
1. Keep backward-compatible CLI command contracts.
2. No secret leakage in structured log fields.
3. Minimal runtime overhead.

## Assumptions to Confirm
1. Keep `print()` output for operator UX while adding parallel structured logs.
2. Event naming convention should stay in `housekeeper.*`/`storage_manager.*` style without introducing a new taxonomy.
3. Existing SEQ env variables (`GOFR_DIG_SEQ_URL`, `GOFR_DIG_SEQ_API_KEY`) remain the activation mechanism.

## Risks and Mitigations
1. Risk: Log volume increase in frequent prune loops.
   - Mitigation: concise event payloads, avoid per-item info unless verbose mode.
2. Risk: Duplicate/noisy signals from both print and logger.
   - Mitigation: ensure print is human summary; logger carries machine fields.
3. Risk: Regressions in tests expecting specific output.
   - Mitigation: add focused tests and avoid changing existing CLI text unless necessary.

## Validation Criteria
1. Targeted tests pass for storage manager logging behavior.
2. Full suite passes via `./scripts/run_tests.sh`.
3. Manual invocation produces structured events with expected keys.
