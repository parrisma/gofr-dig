# Copilot Instructions for gofr-dig

## GENERAL SECTION (ROOT, MACHINE)

ALL RULES ARE MANDATORY.

## A. COMMON PATTERNS, TRUTHS, AXIOMS, BEST PRACTICE

## A1. HARD RULES (MUST/NEVER)

R0 SIMPLICITY: Be brief. Add complexity/verbosity ONLY when needed.
R1 CLARITY: If ambiguous -> ASK. Never guess intent or make design/product decisions.
R2 COLLAB: Treat user as partner. Show enough command output for review; do not hide critical output; do not burn context on noise.
R3 LONG_FORM: If longer than a few sentences -> write `docs/*.md`, not chat.
R4 FORMAT: Technical chat answers are plain text. Markdown is for documents only.
R5 NETWORK: Never use `localhost`. Use Docker service names on `gofr-net`. Host Docker: `host.docker.internal`.
R6 ASCII: ASCII only in code/output. No emoji/Unicode/box drawing.
R7 GIT: Never rewrite pushed history (no `--amend`, no `rebase -i`). Use follow-up commits.
R8 PYTHON: UV only (`uv run`, `uv add`, `uv sync`). No pip/venv.
R9 LOGGING: `StructuredLogger` only. Never `print()` or stdlib `logging`.
R10 NEVER GIT ADD, COMMIT, PUSH ETC unless asked directly

## A2. WORKFLOW (DECISION TREE)

IF change is trivial (few lines, obvious) -> implement directly.
ELSE -> Spec -> Plan -> Execute.

SPEC: `docs/<feature>_spec.md` (WHAT/WHY, constraints, assumptions, no code) -> user approval REQUIRED.
PLAN: `docs/<feature>_implementation_plan.md` (small verifiable steps, no code; update code/docs/tests; run full tests before/after) -> user approval REQUIRED.
EXECUTE: follow plan step-by-step; mark DONE; if uncovered problems appear -> STOP and discuss.

## A3. ISSUE RESOLUTION

IF bug is not an obvious one-line fix -> write `docs/<issue>_strategy.md` BEFORE code.
Strategy MUST include: symptom, hypothesised root cause, assumptions + validation, diagnostics order.
Stay on root cause. Side-issues are recorded, not chased. No root-cause claims without evidence + user validation.

## A4. PLATFORM GROUND TRUTHS

- Network: `gofr-net`. Docker service names only.
- Vault: `http://gofr-vault:8201`. Root token: `lib/gofr-common/secrets/vault_root_token`. Never `localhost` for Vault.
- Auth: shared across services. Vault path `gofr/auth`. JWT audience `gofr-api`.
- Prefer `gofr_common` helpers (auth, config, storage, logging).

## A5. TESTING

- Always use `./scripts/run_tests.sh` (env + service lifecycle). Never raw `pytest`.
- Fix code quality issues before running tests.
- Flags: `--coverage`, `-k "keyword"`, `-v`. Run targeted first, full suite after.
- Fix all failures, even seemingly unrelated ones.
- Improve `run_tests.sh` if it lacks a needed capability.

## A6. ERRORS

- Surface root cause, not side effects.
- Include: cause, context/references, recovery options.
- Register in `RECOVERY_STRATEGIES` (`app/errors/mapper.py`).
- New domain exceptions go in `app/exceptions/`. Do not reuse generic exceptions.

## A7. MCP TOOL PATTERN

In `app/mcp_server/mcp_server.py`, every tool requires:
1. `Tool(...)` in `handle_list_tools` (inputSchema, description, annotations).
2. Routing in `handle_call_tool`.
3. `_handle_<name>(arguments)` -> `List[TextContent]` via `_json_text(...)`.
4. Errors via `_error_response(...)` / `_exception_response(...)` only.

## A8. CODE QUALITY / HARDENING

Review all code as senior engineer + security SME:
- No secrets in code/logs; validate external inputs.
- No unbounded loops/memory; timeouts required; fail closed; least privilege.
- Maintain `test/code_quality/test_code_quality.py` for structural checks.

## A9. PLATFORM SCRIPTS (paths relative to project root)

| Script | Purpose |
|--------|---------|
| `lib/gofr-common/scripts/auth_env.sh` | Export `VAULT_ADDR`, `VAULT_TOKEN`, `GOFR_JWT_SECRET`. Usage: `source <(./lib/gofr-common/scripts/auth_env.sh --docker)` |
| `lib/gofr-common/scripts/auth_manager.sh` | Manage auth groups/tokens (list, create, inspect, revoke). |
| `lib/gofr-common/scripts/bootstrap_auth.sh` | One-time auth bootstrap (groups + initial tokens). |
| `lib/gofr-common/scripts/bootstrap_platform.sh` | Idempotent platform bootstrap (Vault, auth, services). |
| `lib/gofr-common/scripts/manage_vault.sh` | Vault lifecycle: start, stop, status, logs, init, unseal, health. |

## PROJECT SECTION (gofr-dig)

PROJECT_PURPOSE: web scraping and content acquisition service.
RUNTIME: Python (UV).
ENV: VS Code dev container on Docker network `gofr-net`.
MCP_TOOLS: `ping`, `set_antidetection`, `get_content`, `get_structure`, `get_session_info`, `get_session_chunk`, `list_sessions`, `get_session_urls`, `get_session`.

SCRIPTS (use these; do not reinvent workflows):

| Script | Purpose |
|--------|---------|
| `scripts/run_tests.sh` | Run tests (unit, integration, coverage). THE test entry point. |
| `docker/start-prod.sh` | Start (or `--build` and start) the production containers. |
| `docker/stop-prod.sh` | Stop production containers. |
| `scripts/start-test-env.sh` | Spin up ephemeral test services (Vault, SEQ, etc.). |
| `scripts/storage_manager.sh` | Storage management operations. |
| `scripts/backup_now.sh` | Trigger an immediate backup. |
| `scripts/restore_backup.sh` | Restore from a backup. |
| `scripts/list_backups.sh` | List available backups. |
| `scripts/bootstrap_gofr_dig.sh` | Bootstrap gofr-dig environment. |
