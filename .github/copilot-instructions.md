# Copilot Instructions for gofr-dig

These rules are MANDATORY. Violating any rule in the HARD RULES section is a critical failure.

---

## HARD RULES (non-negotiable — follow every time, no exceptions)

1. **NEVER assume — ASK.** If the request is ambiguous, has multiple interpretations, or requires a design decision, stop and ask the user. Do not guess intent.
2. **No `head`, `tail`, or piped truncation on terminal output.** The user needs to see the full output to follow along. Show everything.
3. **Long-form answers go in a document.** If the response is more than a few sentences, write it to a `.md` file in `docs/` (or the relevant directory). Do not dump walls of text into chat.
4. **Plain text for technical answers.** When answering technical questions conversationally, use plain text. Reserve markdown formatting for documents only.
5. **No `localhost`.** This project runs inside a Docker dev container. Always use Docker service names or known host:port pairs. The host Docker daemon is reachable at `host.docker.internal`.
6. **UV only.** Use `uv run`, `uv add`, `uv sync`. NEVER use `pip install`, `python -m venv`, `pip freeze`, or any pip-based workflow.
7. **No `print()`.** Use the project's `StructuredLogger` for all logging. Every log line must be clear, actionable, and include structured context — never cryptic or generic.

---

## CHANGE PROCESS (mandatory for anything beyond a trivial few-line fix)

Follow these three phases IN ORDER. Do NOT skip phases or combine them.

### Phase 1 — Specification
- Write a specification document (`docs/<feature>_spec.md`) describing the proposed changes, constraints, and open questions.
- The spec must NOT contain code. It describes WHAT and WHY, not HOW.
- List every assumption explicitly and ask the user to confirm or reject each one.
- Do NOT proceed until the user approves the spec.

### Phase 2 — Implementation Plan
- Write a step-by-step implementation plan (`docs/<feature>_implementation_plan.md`).
- Steps must be SMALL and independently verifiable — each step should be completable and testable on its own.
- The plan must NOT contain code. It describes the sequence of changes in plain language.
- The plan MUST include:
  - Updating all affected code, docs, and tests.
  - Running the full test suite BEFORE starting (baseline) and AFTER finishing (acceptance).
  - Adding or modifying tests for every behavioral change.
- Do NOT proceed until the user approves the plan.

### Phase 3 — Execution
- Execute the approved plan step by step.
- Mark each step DONE in the plan document as it completes.
- If a step reveals a problem not covered by the plan, STOP and discuss with the user before deviating.

---

## ISSUE RESOLUTION (mandatory for any bug that is not an obvious one-line fix)

1. Write a strategy document (`docs/<issue>_strategy.md`) BEFORE touching code.
   - State the observed symptom and the hypothesised root cause.
   - List every assumption and how each will be validated (logs, tests, inspection).
   - Define a sequence of diagnostic steps.
2. Execute the strategy systematically. Update the document as findings emerge.
3. Stay focused on the root cause. If you discover side-issues, document them in the strategy doc but do NOT chase them until the primary issue is resolved.
4. Ask the user to validate assumptions and findings — do not declare a root cause without evidence.

---

## PROJECT DETAILS

- **Runtime:** Python, managed with UV (`uv run`, `uv add`).
- **Shared library:** Prefer helpers from `gofr_common` (auth, config, storage, logging) over hand-rolled equivalents.
- **Environment:** VS Code dev container. Docker service names and ports — never `localhost`.
- **Host Docker:** Reachable from the dev container at `host.docker.internal`.

---

## TESTING

- **Test runner:** ALWAYS use `./scripts/run_tests.sh`. It sets PYTHONPATH, environment variables, and manages service lifecycle. NEVER run `pytest` directly.
- **Full suite:** `./scripts/run_tests.sh` (no flags) runs everything including integration tests that depend on Vault, SEQ, etc. The script starts and stops these services automatically.
- **Useful flags:** `--coverage`, `-k "keyword"`, `-v` (verbose).
- **Targeted first:** Run targeted tests -k to target new code or code that has issues.
- **Fix what you break.** If tests fail — even tests that appear unrelated to your change — fix them before considering the work complete.
- **Enhance the runner.** If `run_tests.sh` does not support something you need, modify it rather than working around it.
---

## MCP TOOLS

Current tools: `ping`, `set_antidetection`, `get_content`, `get_structure`, `get_session_info`, `get_session_chunk`, `list_sessions`, `get_session_urls`, `get_session`.

### Adding or modifying an MCP tool (mandatory pattern)

Every MCP tool MUST follow this four-step pattern in `app/mcp_server/mcp_server.py`:

1. Add a `Tool(...)` schema in `handle_list_tools` with full `inputSchema`, `description`, and `annotations`.
2. Add routing in `handle_call_tool` to dispatch to the handler.
3. Implement `_handle_<tool_name>(arguments)` returning `List[TextContent]` via `_json_text(...)`.
4. All error paths MUST use `_error_response(code, message, details)` or `_exception_response(exc)`. Never return raw dicts or raise unhandled exceptions.

---

## ERROR HANDLING

- All errors must surface the **root cause**, not a side effect.
- Every error must include: **cause** (what went wrong), **context/references** (relevant IDs, URLs, parameters), and **recovery options** (what the caller can do about it).
- Add the error code to `RECOVERY_STRATEGIES` in `app/errors/mapper.py` with an actionable recovery message.
- Define new exception classes in `app/exceptions/` when the existing ones do not fit. Do NOT reuse generic exceptions for domain-specific failures.

---

## LOGGING

- Use the project's `StructuredLogger` — NEVER `print()`, NEVER the stdlib `logging` module directly.
- Every log message must be **clear and actionable**: a reader should understand what happened and what to do about it without looking at the code.
- Include structured key-value context (url, depth, session_id, duration_ms, etc.) — not just a plain string.

---

## CODE QUALITY AND HARDENING

- After writing code, review it as a **senior engineer and security SME**:
  - No secrets or credentials in code or logs.
  - Input validation on all external inputs.
  - No unbounded loops, unbounded memory growth, or missing timeouts.
  - Safe defaults (fail closed, least privilege).
- Run and enhance `test/code_quality/test_code_quality.py` to enforce structural quality rules (cyclomatic complexity, import hygiene, etc.).

---

## USEFUL SCRIPTS

### Project scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| `scripts/run_tests.sh` | Run tests (unit, integration, coverage). THE test entry point. |
| `scripts/start-prod.sh` | Start (or `--build` and start) the production containers. |
| `scripts/stop-prod.sh` | Stop production containers. |
| `scripts/start-test-env.sh` | Spin up ephemeral test services (Vault, SEQ, etc.). |
| `scripts/storage_manager.sh` | Storage management operations. |

### Platform scripts (`lib/gofr-common/scripts/`)

These are shared across all GOFR projects. Paths are relative to project root.

| Script | Purpose |
|--------|---------|
| `lib/gofr-common/scripts/auth_env.sh` | Mint a short-lived Vault operator token and export `VAULT_ADDR`, `VAULT_TOKEN`, `GOFR_JWT_SECRET`. Use via `source <(./lib/gofr-common/scripts/auth_env.sh --docker)`. |
| `lib/gofr-common/scripts/auth_manager.sh` | Manage auth groups and tokens (list, create, inspect, revoke). Wraps `auth_manager.py`. |
| `lib/gofr-common/scripts/bootstrap_auth.sh` | One-time auth bootstrap — creates reserved groups (`admin`, `public`) and initial tokens in Vault. |
| `lib/gofr-common/scripts/bootstrap_platform.sh` | Idempotent platform bootstrap — guided setup of Vault, auth, and services. |
| `lib/gofr-common/scripts/manage_vault.sh` | Vault lifecycle: `start`, `stop`, `status`, `logs`, `init`, `unseal`, `env`, `jwt-secret`, `bootstrap`, `health`. |
| `lib/gofr-common/scripts/dump_tools_environment.sh` | Dump the complete tools stack environment state for diagnostics. |