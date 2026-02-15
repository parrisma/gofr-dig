# Housekeeper Hardening Spec

## Goal
Improve resilience, robustness, and error handling for storage housekeeping by hardening the existing shell wrapper, Python storage manager, and housekeeper loop while preserving current behavior and interfaces where possible.

This spec defines WHAT will change and WHY. It intentionally does not include code.

## Scope
In scope:
1. Harden `scripts/storage_manager.sh` input handling and shell safety.
2. Harden `app/management/storage_manager.py` prune behavior and operational safety.
3. Harden `app/housekeeper.py` scheduling/error paths and runtime guardrails.
4. Add/update operational documentation for new behavior.
5. Add/modify tests for all behavior changes.

Out of scope:
1. Redesigning `gofr_common.storage.FileStorage` internals.
2. Adding non-storage disk cleanup (e.g., logs retention) unless explicitly approved.
3. Changing MCP tool contracts.

## Problems Observed
1. Housekeeper runtime bug risk: `interval_mins` can be unbound on env parse failure in `app/housekeeper.py`.
2. Wrapper robustness gap: `--env` handling can fail on missing value.
3. Prune accounting gap: entries with missing metadata are skipped from size accounting.
4. Safety gap: no lock to prevent concurrent prune loops.
5. UX gap: declared flags/behavior mismatches (`--yes` on `prune-size` currently no-op).
6. Operational gap: mixed console prints and structured logs reduce consistency.

## Desired End State
1. Housekeeper loop is fail-safe and never crashes due to malformed interval/size env values.
2. Prune operations are single-writer (lock-guarded) per shared storage volume.
3. Storage size checks/deletions are deterministic and report actionable structured logs.
4. CLI wrapper validates required args and fails with clear error messages.
5. CLI command behavior and help text are consistent with actual implementation.
6. Tests cover new/changed behavior and regressions.

## Functional Requirements
1. Housekeeper must wake up every configurable minutes.
2. Housekeeper must evaluate storage usage and prune oldest sessions first until below configurable MB threshold.
3. Housekeeper must log checks and deletions using structured logging for Seq ingestion.
4. Pruning must avoid concurrent execution races against another housekeeper instance.
5. Invalid configuration values must not crash the process; use safe defaults and clear warnings.
6. If no prune is needed, emit a clear status log.

## Non-Functional Requirements
1. Backward-compatible CLI for existing `list`, `stats`, and `purge` commands.
2. Deterministic behavior under repeated runs.
3. No secret leakage in logs.
4. Minimal performance overhead in normal operation.

## Proposed Changes (High Level)
1. Shell wrapper hardening:
   - Add strict shell options and argument validation for `--env`.
   - Improve error messaging when env file/paths are missing.
2. Storage manager hardening:
   - Validate prune inputs robustly.
   - Add lock-based guard for prune execution.
   - Improve accounting/error paths when metadata is missing.
   - Align command options and behavior (`--yes`, docs/help text).
   - Ensure structured logger emits clear check/prune/summary events.
3. Housekeeper hardening:
   - Robust env parsing with fallback defaults.
   - Ensure sleep path is always safe even after exceptions.
   - Log cycle start/end and next wake-up in structured form.
4. Compose/docs updates:
   - Keep housekeeper config variables documented and aligned with behavior.

## Assumptions Requiring Confirmation
1. Deletion policy remains oldest-first based on `created_at` metadata only.
2. If metadata is missing/corrupt, those items should be skipped (not deleted) and logged as anomalies.
3. Target threshold is storage data size (managed session blobs/metadata), not total filesystem free-space watermark.
4. A single lock file in shared storage is acceptable for coordination.
5. `prune-size` should run non-interactively by default (no confirmation prompt).

## Risks and Mitigations
1. Risk: Over-deletion due to bad accounting.
   - Mitigation: conservative accounting + explicit summary logs + tests around thresholds.
2. Risk: Dead/stale lock blocks pruning.
   - Mitigation: lock timeout/stale lock handling and warning logs.
3. Risk: Behavior drift for operators.
   - Mitigation: update docs/help text and add explicit migration notes in docs.

## Validation Criteria
1. Unit tests pass for new validation/locking/error paths.
2. Existing storage manager commands remain functional.
3. Housekeeper handles bad env inputs without crashing.
4. Prune cycle logs include storage usage, purge count, freed bytes/MB, and final size.
5. Full suite passes via `./scripts/run_tests.sh`.
