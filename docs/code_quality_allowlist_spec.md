# Spec: Code quality allowlist JSON

Date: 2026-02-20

## Objective

Move code-quality allowlists out of hard-coded Python constants and into a JSON config file so teams can update allowlisted items without editing the test logic.

This allowlist must be configurable from the command line and have a sensible default.

## Scope

The allowlist controls BOTH:

- Large-file gate allowlist (file paths)
- Radon cyclomatic complexity allowlist (file + function)

## Default location and CLI

- Default allowlist path: test/code_quality/allow.json
- The code quality tests must accept a pytest CLI option:
  - --allowlist-file <path>
  - Default value: test/code_quality/allow.json

Notes:

- The default file name remains allow.json; it is stored under test/code_quality/.
- ./scripts/run_tests.sh supports --allowlist-file and forwards it to the code quality gate.

Path resolution:

- If a relative path is provided, resolve relative to the repo root.

## JSON schema (v1)

Top-level object keys:

1) large_files

- Type: array of strings
- Each string is a repo-relative POSIX path (e.g., "app/mcp_server/mcp_server.py")

2) radon

- Type: array of objects
- Each object:
  - file: string (repo-relative POSIX path)
  - function: string (Radon function name)

Example:

{
  "large_files": [
    "app/mcp_server/mcp_server.py"
  ],
  "radon": [
    {"file": "app/mcp_server/mcp_server.py", "function": "_handle_get_content"},
    {"file": "app/processing/news_parser.py", "function": "_story_from_block"}
  ]
}

## Behavior

- If the allowlist file does not exist:
  - Do not fail.
  - Treat allowlists as empty.
  - Log one warning that the allowlist file was not found and how to create it.

- If the allowlist file exists but cannot be parsed:
  - Fail the code quality gate with a clear error.

- If the allowlist contains invalid entries:
  - Ignore invalid entries but log warnings with enough context to fix them.

## Output requirements

- When an allowlisted item is skipped, emit a structured warning event:
  - code_quality.large_file_allowlisted
  - code_quality.complexity_allowlisted

Each warning must include:

- path
- function (for Radon allowlist)
- recovery guidance (refactor and remove from allowlist)

## Acceptance criteria

- test/code_quality/test_code_quality.py has no hard-coded allowlist entries.
- Running ./scripts/run_tests.sh succeeds with the default allowlist file present.
- Passing --allowlist-file points to an alternate JSON file.
- Missing allowlist file is a warning, not a failure.
