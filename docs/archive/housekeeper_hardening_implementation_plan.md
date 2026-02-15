# Housekeeper Hardening Implementation Plan

## Preconditions
1. Spec approved: `docs/housekeeper_hardening_spec.md`.
2. Assumptions confirmed by user.

## Step-by-Step Plan

1. Baseline test run — DONE
   - Run `./scripts/run_tests.sh` to capture pre-change baseline.
   - Record failures (if any) without making changes.
   - Verification: baseline result captured.
   - Outcome: captured baseline with 1 existing failure (`test/code_quality/test_code_quality.py::test_no_type_errors`).

2. Harden shell wrapper argument handling — DONE
   - Update `scripts/storage_manager.sh` to validate `--env` value presence/allowed values.
   - Add safer shell options and explicit failure messages for missing env file/root vars.
   - Verification: wrapper prints actionable errors on invalid invocation.

3. Harden prune-size command input and behavior — DONE
   - Update `app/management/storage_manager.py` to enforce robust validation for `--max-mb`.
   - Remove/align misleading flags and help text for `prune-size`.
   - Keep behavior non-interactive and deterministic.
   - Verification: CLI help and runtime behavior are consistent.

4. Add prune concurrency guard — DONE
   - Implement file-based locking around prune execution in storage manager path.
   - Add stale-lock handling and structured warning/error logs.
   - Verification: second concurrent invocation exits safely with clear message.

5. Improve accounting and anomaly handling — DONE
   - Handle missing/corrupt metadata entries with explicit structured anomaly logs.
   - Ensure pruning loop and summary remain correct under partial metadata issues.
   - Verification: tests prove no crash and correct summary fields.

6. Harden housekeeper runtime loop — DONE
   - Update `app/housekeeper.py` to safely parse env values with defaults.
   - Ensure cycle always computes a safe sleep interval.
   - Log cycle status and next wake-up using structured logging.
   - Verification: invalid env values do not crash process.

7. Update docs — DONE
   - Update `docs/housekeeper.md` and relevant README/getting-started references to reflect final behavior and configuration.
   - Verification: docs match implementation and command help.

8. Add/modify tests for changed behavior — DONE
   - Add targeted tests for wrapper behavior (if existing pattern permits).
   - Add unit tests for prune input validation, lock handling, metadata anomalies, and housekeeper env parsing.
   - Verification: targeted tests pass.
   - Outcome: added `test/session/test_storage_housekeeping.py`; targeted run passed.

9. Acceptance test run — DONE
   - Run `./scripts/run_tests.sh` post-change.
   - Resolve regressions caused by this work.
   - Verification: full suite passes or report precise remaining blockers.
   - Outcome: full suite passed (`504 passed`).

## Definition of Done
1. All steps above completed and validated.
2. Behavior is robust against malformed config and concurrent prune runs.
3. Logs are actionable and structured for operations.
4. Tests and docs are updated and consistent.
