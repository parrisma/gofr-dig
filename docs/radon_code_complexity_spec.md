# Spec: Radon code complexity gate (code quality)

Date: 2026-02-19

## Objective

Add a pragmatic Radon-based cyclomatic complexity (CC) gate to the existing code quality tests (test/code_quality) so CI provides actionable feedback when functions become too complex.

The gate must be:

- Low-noise (fails only for clearly excessive complexity)
- Deterministic and LLM-friendly (structured output, no raw Radon text dumps)
- Implemented as a single test in test/code_quality/test_code_quality.py (no duplicate complexity checks)

## Scope

- Analyze Python code under:
  - app/
- Exclusions:
  - test/ is excluded
  - __init__.py files are excluded
  - lib/gofr-common is excluded

## Tooling

- Use Radon CLI.
- Install via UV dev dependency:
  - uv add --group dev radon

## Rules (thresholds)

Radon CC grades are standard:

- A: 1-5
- B: 6-10
- C: 11-20
- D: 21-30
- E: 31-40
- F: 41+

Gate policy:

- Fail if any function/method is grade E or F anywhere in scope.
- Fail if any function/method is grade D AND it is in app/.
- Do not fail for grade C (informational only, and only shown when failing for other reasons).

## Pragmatic rollout / allowlist

To avoid forcing immediate large refactors when introducing the gate:

- The gate may include a small explicit allowlist of known existing offenders (file + function name).
- Allowlisted offenders must still be reported as warnings in the failure output (or via logger), with a recovery message.

Default stance:

- Prefer no allowlist.
- If the first Radon run would fail on existing code, introduce the smallest allowlist necessary.

## Output requirements (LLM-friendly)

If failing, output should:

- Be short and stable.
- List only the top offenders (e.g., max 10), sorted by severity (grade then CC).
- Emit deterministic blocks like:

COMPLEXITY_VIOLATION
file: app/foo/bar.py
function: WidgetBuilder.build
line: 123
cc: 34
grade: F
why: cyclomatic complexity exceeds allowed threshold
action: split into helper functions; reduce nesting via early returns; separate IO from parsing

Include a prompt seed line:

To remediate: open the file/function above and refactor to reduce branching; keep behavior identical; add/adjust tests.

## Acceptance criteria

- One new test runs Radon CC and enforces the thresholds.
- No duplicate Radon/complexity tests exist in test/code_quality/test_code_quality.py.
- ./scripts/run_tests.sh remains green after adding the gate (using allowlist only if needed for existing code).
- Failure output is deterministic and actionable.
