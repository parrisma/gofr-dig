# Proposal: Share AppRole + Bootstrap Building Blocks via gofr-common

Date: 2026-02-15

## Goal
All GOFR projects need consistent, repeatable bootstrap behavior for:
- shared platform infra (Vault, networks, volumes)
- AppRole policy/role provisioning and self-healing policy sync
- seeding project secrets into the shared secrets volume

This proposal identifies what can be parameterized and moved into gofr-common, using [scripts/bootstrap_gofr_dig.sh](../scripts/bootstrap_gofr_dig.sh) and [tmp/bootstrap_gofr_doc.sh](../tmp/bootstrap_gofr_doc.sh) as reference implementations.

## Current State (Observed)

### Common patterns already duplicated
Both scripts implement essentially the same orchestration framework:
- argument parsing (`--yes`, `--trace`, `--log-file`, `--no-log`, `--start-*`, `--run-tests`)
- logging helpers (`info/ok/warn/err`)
- `run_step()` sequencing + timing
- prerequisite checks (git clone, docker engine, docker compose)
- `ensure_submodule()` for `lib/gofr-common`
- `run_platform_bootstrap()` calling `lib/gofr-common/scripts/bootstrap_platform.sh`
- project image build checks / build scripts
- `ensure_vault_healthy()` safety net
- ensure AppRole creds
- optional “seed secrets volume” step

### Key divergence worth standardizing
The doc variant includes a portable secrets discovery mechanism:
- `resolve_secrets_dir()` and `require_vault_bootstrap_artifacts()`
- supports env override and shared volume (`/run/gofr-secrets`)

The dig variant has hardcoded file probing in a few places instead.

### AppRole provisioning is currently project-specific
- `scripts/ensure_approle.sh` and `scripts/setup_approle.py` are project-local.
- Service/role/policy mapping is embedded in project code (e.g., gofr-dig provisions `gofr-dig` and `gofr-admin-control`).

## Proposed Direction
Move shared mechanics into gofr-common; keep project-specific identity and service mapping as configuration.

### A. Shared “bootstrap framework” in gofr-common (bash library)
Add a small bash library in gofr-common that projects source.

Proposed new files in gofr-common:
- `lib/gofr-common/scripts/lib/bootstrap_lib.sh`

What it contains (shared, parameterizable):
- argument parsing helpers for the common flags
- standardized logging + `--log-file` + `--trace`
- `run_step()` and `confirm()`
- prerequisite checks:
  - `require_docker()`
  - `ensure_git_clone()` (optional; some projects may be vendored)
  - `ensure_submodule()` (optional; can be disabled if gofr-common is vendored)
- secrets discovery:
  - `resolve_secrets_dir()`
  - `require_vault_bootstrap_artifacts()`
- a robust `ensure_vault_healthy()` implementation that:
  - starts Vault if missing
  - waits until unsealed
  - validates KV v2 at `secret/`
  - validates JWT signing secret
  - validates AppRole auth enabled

This turns the project bootstrap scripts into thin wrappers.

Parameterization model:
- project script sets variables and supplies project callbacks.

Example parameters the project wrapper provides:
- `GOFR_PROJECT_SLUG` (e.g., `dig`, `doc`, `plot`)
- `GOFR_PROJECT_NAME` (display)
- image names (`gofr-dig-dev`, `gofr-dig-prod`)
- commands/paths for:
  - build dev image
  - build prod image
  - start dev container
  - start prod stack
  - run tests
  - seed secrets volume

Result:
- each project keeps a tiny `scripts/bootstrap_<project>.sh`
- the duplicated orchestration logic lives in one place

### B. Standardize AppRole provisioning as “config + one runner”
Today, `setup_approle.py` encodes:
- a fixed `SERVICES` dict
- fixed policy attachment pattern

Proposal:
- move the “AppRole provisioning runner” into gofr-common
- make it driven by a per-project config file

Proposed new files in gofr-common:
- `lib/gofr-common/src/gofr_common/auth/provisioning.py` (library)
- `lib/gofr-common/scripts/setup_approle.py` (CLI runner)
- `lib/gofr-common/scripts/ensure_approle.sh` (optional wrapper)

Per-project config (in the project repo):
- `config/gofr_approles.json` (or `.yaml` if you prefer)

Suggested config schema:
- `project`: string (display)
- `vault`:
  - `mount_point`: default `approle`
  - `token_ttl`, `token_max_ttl`
- `roles`: list of:
  - `role_name` (e.g., `gofr-dig`)
  - `policies`: list of policy names (e.g., `gofr-dig-policy`, `gofr-dig-logging-policy`)
  - `credentials_output_name` (filename without `.json`) if different from role name

Behavior the runner supports:
- full provision (policies + roles + new credentials)
- `--policies-only` (policies + roles only)
- `--check` (validate credentials existence)

Benefits:
- the self-healing “policy sync without regenerating creds” becomes consistent across projects
- adding a new project is config-only, not copy/paste of Python + bash

### C. Align where credentials live and how they’re discovered
Currently, multiple locations are used:
- project `secrets/service_creds/*.json` (volume-backed)
- fallback `lib/gofr-common/secrets/service_creds/*.json`
- optionally `/run/gofr-secrets`

Proposal:
- codify the search path in one place (gofr-common), in this priority order:
  1) `GOFR_SHARED_SECRETS_DIR` (explicit override)
  2) `/run/gofr-secrets` (shared volume mount)
  3) `${PROJECT_ROOT}/secrets` (project mount)
  4) `${PROJECT_ROOT}/lib/gofr-common/secrets` (bootstrap artifacts)

And codify a single “credentials output dir” for running services:
- `${PROJECT_ROOT}/secrets/service_creds/`

This reduces drift and avoids projects inventing new “where is the root token?” logic.

### D. Make “seed secrets volume” a standardized hook
Both scripts treat secrets seeding as optional.

Proposal:
- define a shared function in gofr-common that does:
  - if project provides `scripts/migrate_secrets_to_volume.sh`, run it
  - else, print a consistent message and exit 0

This standardizes the semantics (optional step should not fail).

### E. Ports and service addresses
`lib/gofr-common/config/gofr_ports.env` is already the shared source of truth.

Proposal:
- keep ports there
- add a shared helper that yields service URLs based on:
  - docker service name (not `localhost`)
  - selected port set (prod vs test)

Notes:
- today some scripts print `http://localhost:PORT` on completion; in a devcontainer-based workflow this is frequently wrong. Standardizing an “address printer” would reduce confusion.

## What stays project-specific
These should remain in each project repo (thin wrappers):
- project-specific images/build scripts and docker compose files
- project-specific service list (MCP/MCPO/Web vs others)
- any project-specific secret seeding logic
- project-specific “test command” (still via `./scripts/run_tests.sh`)

## Migration Plan (High level)
1) Implement `bootstrap_lib.sh` in gofr-common with:
   - secrets discovery
   - vault health check
   - standardized logging + steps
2) Convert one project (gofr-dig) to use the library (thin wrapper script).
3) Extract AppRole provisioning runner into gofr-common.
4) Add per-project role config (`config/gofr_approles.json`) and switch projects to use it.
5) Convert other projects one-by-one and delete duplicated bootstrap logic.

## Open Questions (need confirmation)
1) Canonical AppRole interface: should every project call `ensure_approle.sh` (bash) or `setup_approle.py` (python) directly?
2) Role naming convention: do we want one AppRole per runtime container (`mcp`, `web`, etc.) or one per project (`gofr-dig`), with policies partitioning within Vault paths?
3) Credentials rotation strategy: will we ever want automatic rotation (e.g., regenerate SecretIDs) as part of bootstrap, or keep it explicit only?
4) Config format preference: JSON vs YAML for the per-project AppRole role list.

## Concrete next step
If you agree with this direction, I can draft the first shared artifact in gofr-common:
- `scripts/lib/bootstrap_lib.sh`
- and update gofr-dig’s `scripts/bootstrap_gofr_dig.sh` to source it and provide only project parameters.
