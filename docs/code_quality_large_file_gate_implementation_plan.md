# Implementation plan: Large source file gate (code quality)

Date: 2026-02-19

## Baseline

1) Run the full test suite:

- ./scripts/run_tests.sh

## Steps

2) Add a new pytest check to the existing code quality test suite:

- Update test/code_quality/test_code_quality.py
- Add a test that scans app/ for *.py
- Exclude __init__.py
- Count physical lines per file
- Fail if any file exceeds 1000 lines
- Add a small allowlist for existing large files (initially app/mcp_server/mcp_server.py)
- Failure message must be short, stable, and actionable

3) Validate locally

- Run ./scripts/run_tests.sh

4) Commit and push

- Commit only the intended changes
- Push to origin/main

## Completion criteria

- Gate is active under test/code_quality
- Output is actionable and LLM-friendly
- Full test suite remains green
