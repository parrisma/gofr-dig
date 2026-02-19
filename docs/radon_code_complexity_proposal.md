# Pragmatic Radon integration proposal (code complexity)

Date: 2026-02-19

## Goal

Add actionable, low-noise complexity feedback to the existing code-quality gate in test/code_quality so we catch complexity regressions early while avoiding constant churn.

This proposal focuses on Radon (cyclomatic complexity and maintainability index) and aligns with the current pattern in test/code_quality/test_code_quality.py (run a tool via subprocess, fail with a clear, actionable message).

## Why Radon (and what it should do for us)

Radon is useful when it is used as a guardrail, not a purity test.

Pragmatic outcomes:

- Highlight functions that are becoming hard to understand/test.
- Prevent extreme complexity (the "this should be split" cases).
- Provide consistent feedback in CI without blocking normal iteration on reasonable refactors.

Non-goals:

- Do not force a global rewrite of existing code.
- Do not fail CI for minor complexity changes.

## Proposed approach

### 1) Add Radon as a dev dependency (UV)

Use the repo standard dependency-group mechanism:

- uv add --group dev radon

Rationale:

- test/code_quality already assumes tooling can be provided via .venv (ruff, pyright).
- CI/dev container can install dev dependencies consistently.

### 2) Add one new code quality test

Add a new pytest test in test/code_quality/test_code_quality.py:

- test_complexity_is_reasonable()

The test should:

- Run Radon CC (cyclomatic complexity) against these directories:
  - app
  - simulator
  - scripts
- Use JSON output to avoid fragile parsing.
- Parse JSON and emit a deterministic summary (do not print raw Radon output).
- Fail only when complexity is clearly excessive (see thresholds below).

Implementation shape (conceptual):

- Resolve radon executable from .venv/bin/radon (like ruff/pyright resolution)
- subprocess.run([radon, "cc", ...])
- subprocess.run([radon, "cc", ...])
- Parse JSON output
- Collect offenders and fail with a compact report + recovery guidance

### 3) Threshold policy (pragmatic defaults)

Cyclomatic complexity grading (Radon standard):

- A: 1-5 (simple)
- B: 6-10 (acceptable)
- C: 11-20 (watch)
- D: 21-30 (needs refactor)
- E/F: 31+ (must refactor)

Proposed CI gate:

- Fail if any function/method is grade E or F.
- Fail if any function/method is grade D AND it is in app/ (service code).
- Do not fail for C grades (report in the failure message only if failing anyway).

This keeps the rule focused on extreme cases and avoids noisy failures.

Optional future tightening (after observing data for 1-2 weeks):

- Fail if more than N functions in app/ are grade D.

### 4) Maintainability index (MI) policy (optional)

MI can be valuable, but it tends to be noisier.

If enabled, start with a single guardrail:

- Fail only if any file in app/ has MI < 10.

Everything else should be informational only.

### 5) Exclusions / scope control

To keep signal high:

- Exclude test/ from Radon checks (tests can be complex and are not runtime critical).
- Exclude __init__.py (often trivial and sometimes confusing to grade).
- Do not scan lib/gofr-common (submodule) as part of gofr-dig complexity gates.

### 6) Developer UX

The failure message should be actionable and consistent with existing code-quality tests.

Primary principle:

- Make output structured, minimal, and action-oriented so a human (or LLM) can take remediation action quickly.

Concrete requirements:

- Use JSON output from Radon (not human text output). Parse it and emit your own summary.
- Report only the top offenders and only when failing (avoid noisy FYI spam).
- For each offender, include fields that support remediation:
  - file path
  - function/method name (qualified if possible)
  - line number (start line)
  - CC score and grade (D/E/F)
  - short “why it failed” sentence
  - 2-3 concrete refactor suggestions (generic patterns, not code)

- Show the top offenders, with:
  - file path
  - function name
  - CC score and grade
- Provide recommended recovery actions:
  - Extract helper functions
  - Reduce nesting via early returns
  - Split parsing/IO logic

Deterministic failure block format (example):

COMPLEXITY_VIOLATION
file: app/foo/bar.py
function: WidgetBuilder.build
line: 123
cc: 34
grade: F
why: cyclomatic complexity exceeds allowed threshold
action: split into helper functions; reduce nesting via early returns; separate IO from parsing

Include one copy/paste prompt seed line in the failure output:

To remediate: open the file/function above and refactor to reduce branching; keep behavior identical; add/adjust tests.

Local run instructions:

- uv run radon cc -s -a app simulator scripts

## Relationship to large-file detection

Radon primarily detects complex functions, not “very large modules” directly.

If the project wants to detect very large source files, use a separate large-file gate in test/code_quality (line-count based), which is more reliable and less surprising than inferring file size from CC/MI.

## Proposed acceptance criteria

- A new code quality test runs Radon in CI.
- CI fails only for truly extreme complexity (grade E/F, or grade D in app/).
- The error output clearly identifies what to refactor and where.
- Developers can reproduce locally with a single uv command.

## Risks and mitigations

- Risk: false positives / noisy failures
  - Mitigation: fail only at high thresholds (D/E/F) and restrict scope to app/.

- Risk: tool availability
  - Mitigation: install via uv dev dependency and resolve from .venv/bin first.

- Risk: performance
  - Mitigation: limit scan directories; Radon is typically fast on this size repo.
