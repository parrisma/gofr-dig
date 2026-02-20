# Implementation plan: Code quality allowlist JSON

Date: 2026-02-20

## Baseline

1) Run full test suite:

- ./scripts/run_tests.sh

## Steps

2) Add default allowlist file

- Create test/code_quality/allow.json with current allowlisted items:
  - large_files: app/mcp_server/mcp_server.py
  - radon: (app/mcp_server/mcp_server.py, _handle_get_content)
  - radon: (app/processing/news_parser.py, _story_from_block)

3) Add pytest CLI option

- Add conftest integration for pytest option:
  - --allowlist-file (default test/code_quality/allow.json)

4) Update code quality tests to load allowlist from JSON

- Update test/code_quality/test_code_quality.py:
  - Remove hard-coded allowlist constants
  - Load allowlist once per test session (fixture)
  - Wire into:
    - large-file gate
    - Radon CC gate
  - Preserve structured warning logs for allowlisted skips

5) Validate

- Run ./scripts/run_tests.sh

6) Commit and push

- Commit:
  - allow.json
  - conftest changes
  - code quality test changes
  - spec/plan docs
- Push to origin/main

## Completion criteria

- Default behavior uses test/code_quality/allow.json.
- CLI override works.
- No duplicated allowlist logic.
- Full suite passes.
