# Storage Manager SEQ Logging Implementation Plan

## Preconditions
1. Spec approved: `docs/storage_manager_seq_logging_spec.md`.
2. Assumptions confirmed by user.

## Steps

1. Baseline tests — DONE
   - Run `./scripts/run_tests.sh` to capture pre-change baseline.
   - Record any existing failures before edits.
   - Outcome: baseline passed (`504 passed`).

2. Add command lifecycle structured events — DONE
   - Update `app/management/storage_manager.py` to log `command_start` and `command_end` with command name, storage_dir, group, and status code.
   - Keep CLI behavior unchanged.

3. Add structured validation and branch events — DONE
   - Emit structured warnings/errors for input validation failures and notable branches (`empty_storage`, `lock_busy`, `target_unmet`).
   - Ensure each non-zero return path emits a structured event with cause/context.

4. Normalize prune summary fields — DONE
   - Ensure prune summary event always includes stable counters: `item_count`, `deleted_count`, `freed_mb`, `final_mb`, `target_mb`, `anomalies`, `exit_code`.
   - Keep per-item logs gated by existing verbosity behavior where practical.

5. Add/modify tests — DONE
   - Add targeted tests that assert structured events for key paths (success, validation failure, lock busy, target unmet).
   - Reuse existing logging test patterns where possible.
   - Outcome: added assertions in `test/session/test_storage_housekeeping.py` for validation and command lifecycle events.

6. Update docs — DONE
   - Update `docs/housekeeper.md` and/or relevant operations docs to mention storage manager events in SEQ and key event names.

7. Acceptance validation — DONE
   - Run targeted tests first.
   - Run full suite with `./scripts/run_tests.sh`.
   - Fix regressions introduced by this change.
   - Outcome: targeted unit run passed (`473 passed, 33 deselected`), full suite passed (`506 passed`).

## Definition of Done
1. Storage manager command lifecycle and critical outcomes are consistently structured-logged.
2. Tests pass and document expected log behavior.
3. Docs reflect how to observe these events in SEQ.
