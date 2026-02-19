# Spec: Large source file gate (code quality)

Date: 2026-02-19

## Objective

Add a pragmatic, deterministic code-quality gate that detects very large Python source files and fails CI early, producing LLM-friendly remediation output.

This is complementary to Ruff/Pyright and Radon:

- Ruff/Pyright catch correctness and style issues.
- Radon catches high-complexity functions.
- This gate catches "this file is becoming unreviewable" situations.

## Scope

- Directory: app/
- File type: *.py
- Exemptions:
  - Exempt __init__.py

## Rule

Fail code quality if any Python file in app/ (excluding __init__.py) exceeds:

- 1000 lines

Pragmatic rollout:

- Existing large files may be temporarily allowlisted to avoid forcing immediate refactors.
- The gate still applies to those files once they are refactored (remove from allowlist).

Initial allowlist:

- app/mcp_server/mcp_server.py (existing 2000+ line module)

Line counting method:

- Count physical lines in the file (splitlines), not logical statements.

## Output requirements

On failure, output must be actionable and consistent:

- Include a stable error code string: LARGE_SOURCE_FILE
- List each offending file with:
  - file path
  - line_count
  - limit
- Provide brief remediation guidance:
  - split into modules
  - extract helpers
  - isolate IO vs parsing vs business logic

## Assumptions

- The goal is pragmatic feedback, not perfect measurement.
- app/ is the highest value scope for runtime maintainability.

## Acceptance criteria

- Running ./scripts/run_tests.sh fails when an app/ Python file exceeds 1000 lines (excluding __init__.py and allowlist).
- Failure output clearly identifies which file(s) exceeded the limit and what to do next.
- No impact on existing passing builds unless a file violates the threshold.
