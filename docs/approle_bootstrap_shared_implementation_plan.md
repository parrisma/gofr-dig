# Implementation Plan: Shared AppRole + Bootstrap Components in gofr-common

Date: 2026-02-15

This document is Phase 2 (Implementation Plan). It describes the sequence of changes only (no code).

## Preconditions
- All Python execution in automation uses `uv run` / `uv sync` / `uv add`.
- No scripts should log secrets (Vault tokens, SecretIDs, JWTs).
- Docker service names are used for in-container addresses (no `localhost` when targeting container-to-container).
- Secrets seeding into the shared secrets volume is REQUIRED for now.

## Scope
In scope:
- Shared AppRole provisioning entrypoint in gofr-common (Python, called via `uv run`).
- Shared secrets discovery logic (shared volume/env override/project secrets/submodule fallback).
- A per-project JSON config that describes “AppRole per PROJECT” roles/policies.
- Update gofr-dig to use the shared entrypoint as the pilot migration.

Out of scope (for this iteration):
- A fully shared “bootstrap_everything.sh” that builds/starts arbitrary projects.
- Automatic credential rotation beyond explicit full-provisioning.
- Removing the secrets seeding step or changing runtime mounting conventions.

## Deliverables
- gofr-common: one canonical Python entrypoint for AppRole provisioning + policy sync.
- gofr-dig: uses shared entrypoint (removes project-specific provisioning logic where possible).
- A stable JSON schema for project AppRole configuration.
- Tests covering config parsing and `--policies-only` behavior.

## Step-by-step Plan

### Step 0 — Baseline tests (before any code changes)
- Run the full suite via `./scripts/run_tests.sh`.
- Record pass/fail status.

Status: DONE (2026-02-15) — `./scripts/run_tests.sh` → 506 passed

DONE criteria:
- Baseline status captured.

### Step 1 — Define the per-project JSON schema
- Create a concise schema definition (documented in gofr-common) that supports:
  - project identifier (string)
  - required roles list
  - policy names per role
  - credential output filename per role (defaults to role name)
  - default TTL settings (optional)
- Decide the on-disk location convention for each project config file (e.g., `config/gofr_approles.json`).

Status: DONE (2026-02-15) — schema doc added in gofr-common; example config added for gofr-dig

DONE criteria:
- Schema documented.
- One example config drafted for gofr-dig.

### Step 2 — Implement shared secrets discovery in gofr-common
- Create a shared function/module that resolves the secrets directory using this precedence:
  1) `GOFR_SHARED_SECRETS_DIR`
  2) `/run/gofr-secrets`
  3) `${PROJECT_ROOT}/secrets`
  4) `${PROJECT_ROOT}/lib/gofr-common/secrets`
- Expose a single API to return:
  - root token path/value (without printing)
  - unseal key path/value (without printing)

Status: DONE (2026-02-15) — shared discovery + safe read helpers added in gofr-common

DONE criteria:
- One shared implementation used by the provisioning entrypoint.
- No other project keeps bespoke “hunt for vault_root_token” logic.

### Step 3 — Implement canonical shared Python entrypoint in gofr-common
- Add a gofr-common script/CLI that:
  - loads the project JSON config
  - resolves Vault URL (service name + port from gofr_ports.env)
  - authenticates as Vault root (from secrets discovery)
  - enables AppRole auth (idempotent)
  - installs policies (idempotent)
  - syncs roles and attached policies (idempotent)
  - writes credentials files for the configured roles (full-provision mode)
  - supports `--policies-only` (no credential regeneration)
  - supports `--check` (validate credentials exist)
  - exits non-zero with actionable error messages

Status: DONE (2026-02-15) — shared config loader + shared `setup_approle.py` added in gofr-common

DONE criteria:
- Supports both initial provisioning and safe “policy sync only”.
- No secrets are logged.

### Step 4 — Add/adjust tests in gofr-common
- Unit tests for:
  - JSON config parsing/validation (missing fields, wrong types, empty role list)
  - `--policies-only` ensures policy/role sync is invoked without credential writes
  - secrets discovery precedence and missing-artifact errors

Status: DONE (2026-02-15) — targeted unit tests added; code quality gate + unit suite passing

DONE criteria:
- Tests pass locally via the project test harness (`./scripts/run_tests.sh --unit ...`).

### Step 5 — Pilot migration: gofr-dig adopts shared entrypoint
- Add `config/gofr_approles.json` to gofr-dig describing the “per PROJECT” roles:
  - `gofr-dig` with its policies (including logging policy if required)
  - `gofr-admin-control` with admin control policy
- Update gofr-dig scripts to call the shared gofr-common python entrypoint via `uv run`.
- Ensure `start-prod.sh` triggers the self-healing path (policy sync) on every start.
- Ensure secrets seeding is enforced (hard fail) in the bootstrap flow until replaced.

DONE criteria:
- `start-prod.sh` starts successfully with existing creds and applies updated policies.
- A “policy change in gofr-common” can be applied without regenerating credentials.

Status: DONE (2026-02-15) — gofr-dig uses shared gofr-common `setup_approle.py` + `config/gofr_approles.json`; start-prod self-heals via policies-only

### Step 6 — Acceptance tests (after changes)
- Run targeted unit tests first.
- Run the full suite via `./scripts/run_tests.sh`.

Status: DONE (2026-02-15) — `./scripts/run_tests.sh` → 517 passed

DONE criteria:
- Test suite is green.

### Step 7 — Rollout plan for other GOFR projects (no code yet)
- Create a short checklist per project:
  - Add `config/gofr_approles.json`:
    - `project`: `gofr-<project>`
    - `roles`: include `gofr-<project>` and `gofr-admin-control` (per-project model)
  - Update project `ensure_approle.sh` (or equivalent) to call:
    - `uv run lib/gofr-common/scripts/setup_approle.py --project-root <root> --config config/gofr_approles.json`
    - Use `--policies-only` when creds already exist (self-healing)
  - Ensure `start-prod.sh` (or equivalent) calls `ensure_approle.sh` during startup.
  - Ensure project bootstrap enforces secrets seeding (required step for now).
  - Remove or stop calling any project-local AppRole provisioning scripts once validated.
  - Run acceptance tests: `./scripts/run_tests.sh`.

DONE criteria:
- Checklist exists and is consistent.

Status: DONE (2026-02-15)

## Risk / Rollback
- Risk: changing AppRole provisioning can break running services if credentials are regenerated unexpectedly.
  - Mitigation: default startup path uses `--policies-only` when creds already exist.
- Rollback: keep existing project-local scripts until the pilot is validated; allow switching back by calling the old script.

## Open Questions (confirm before execution)
- Credential output location: should credentials always be written only to `${PROJECT_ROOT}/secrets/service_creds/` (volume-backed), with fallback reads only?
- Should the shared entrypoint update roles for policies that don’t exist yet, or fail hard with an explicit error?
- Naming: should the shared entrypoint live under `lib/gofr-common/scripts/` or under `lib/gofr-common/src/...` with a small runner script?
