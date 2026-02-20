# Code quality gates

This folder contains the code-quality gate used by the project test runner.

The gate is implemented in `test/code_quality/test_code_quality.py` and is run first by `./scripts/run_tests.sh`.

## How to run

Preferred (project standard):

- `./scripts/run_tests.sh`

Run only the code quality gate:

- `./scripts/run_tests.sh test/code_quality/`

## What is enforced

The code quality gate currently enforces:

- Ruff: no lint errors.
- Pyright: no type errors.
- Syntax: all Python files parse.
- Large source file limit (app/ only): fails if any `app/**/*.py` (excluding `__init__.py`) exceeds 1000 lines.
- Radon cyclomatic complexity (app/ only): runs `radon cc -j app` and fails on high-severity grades (D/E/F).

Notes:

- The large-file and Radon gates are intentionally scoped to runtime code under `app/`.
- Allowlisted items are not silent: they emit structured warnings with recovery guidance.

## Allowlist JSON

Some existing hotspots are allowlisted to enable incremental cleanup.

Default allowlist file:

- `test/code_quality/allow.json`

Override allowlist file:

- `./scripts/run_tests.sh --allowlist-file path/to/allow.json`
- Or directly via pytest option: `uv run python -m pytest test/code_quality/test_code_quality.py -v --allowlist-file path/to/allow.json`

Path rules:

- If `--allowlist-file` is relative, it is resolved relative to the repo root.
- Allowlist entries use repo-relative POSIX paths (for example: `app/mcp_server/mcp_server.py`).

Schema (v1):

- `large_files`: array of strings (file paths)
- `radon`: array of objects `{ "file": "...", "function": "..." }`

Example:

{
  "large_files": [
    "app/mcp_server/mcp_server.py"
  ],
  "radon": [
    {"file": "app/mcp_server/mcp_server.py", "function": "_handle_get_content"}
  ]
}

Behavior:

- Missing allowlist file: does not fail the gate; allowlists are treated as empty and a warning is logged.
- Invalid JSON: fails the gate with a clear parse error.
- Invalid entries: ignored with warnings so the file can be fixed.
