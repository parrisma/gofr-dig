# Implementation plan: Radon code complexity gate (code quality)

Date: 2026-02-19

## Baseline

1) Run the full test suite:

- ./scripts/run_tests.sh

## Steps

2) Add Radon as a dev dependency (UV)

- uv add --group dev radon

3) Add a single Radon CC gate to test/code_quality

- Update test/code_quality/test_code_quality.py
- Add a radon_executable fixture (resolve from .venv/bin first)
- Add exactly one new test:
  - test_no_excessive_cyclomatic_complexity (name can vary, but must be single)
- The test must:
 - The test must:
  - run Radon with JSON output
  - parse JSON
  - apply thresholds:
    - E/F anywhere fails
    - D in app/ fails
  - emit deterministic, LLM-friendly failure output with top offenders only

4) Pragmatic rollout adjustment (only if needed)

- Run the code quality gate.
- If it fails due to existing offenders:
  - add the smallest explicit allowlist (file + function name)
  - rerun

5) Validate

- Run ./scripts/run_tests.sh

6) Commit and push

- Commit only intended changes (deps + test + docs updates if any)
- Push to origin/main

## Completion criteria

- Radon complexity gate is active and non-duplicated.
- Output is actionable.
- Full test suite passes.
