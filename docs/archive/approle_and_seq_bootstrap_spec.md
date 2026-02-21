# Spec: AppRole Provisioning + SEQ Secret Bootstrap

Status: Approved (implemented)

## Objective
Make first-run bootstrap on a new machine fully operational by:
1) provisioning required Vault AppRoles/credentials as part of the main bootstrap flow, and
2) providing a dedicated script to seed SEQ logging sink secrets into Vault.

## Problem Statement
- A fresh checkout can start the stack, but logging may be degraded because SEQ sink secrets are missing in Vault.
- AppRole provisioning is currently conditional and may not guarantee that all required roles (including admin-control) are provisioned.
- There is no single, obvious bootstrap entry point to write SEQ secrets into Vault.

## Non-Goals
- Do not require pasting Vault root token/unseal key values into chat or code.
- Do not widen runtime policies beyond least privilege.
- Do not make runtime services depend on Vault root token.

## Current Behavior (Observed)
- `scripts/bootstrap_gofr_dig.sh`:
  - bootstraps platform and verifies Vault health.
  - calls `ensure_approle_creds` which checks only for `secrets/service_creds/gofr-dig.json` (or gofr-common fallback) and then runs `scripts/ensure_approle.sh`.
- `docker/start-prod.sh`:
  - attempts to read SEQ secrets from Vault:
    - `secret/gofr/config/logging/seq-url` field `value`
    - `secret/gofr/config/logging/seq-api-key` field `value`
  - if either is missing, continues in degraded logging mode.

## Proposed Changes

### 1) Ensure AppRole provisioning runs as part of bootstrap
- Add/replace a bootstrap step so that `scripts/bootstrap_gofr_dig.sh` runs `uv run scripts/setup_approle.py` as part of normal bootstrap.
- The step should be idempotent and safe to run multiple times.
- Inputs:
  - Vault URL and token should be resolved via environment + `secrets/vault_root_token` fallback (same pattern used elsewhere).
- Outputs:
  - `secrets/service_creds/gofr-dig.json` exists
  - `secrets/service_creds/gofr-admin-control.json` exists

### 2) Add `bootstrap_seq.sh` to seed SEQ secrets in Vault
- Create a new script (target location: `lib/gofr-common/scripts/bootstrap_seq.sh` or project-local `scripts/bootstrap_seq.sh` — see Open Questions) that writes:
  - `secret/gofr/config/logging/seq-url` (field `value`)
  - `secret/gofr/config/logging/seq-api-key` (field `value`)
- The script must:
  - require the operator to provide SEQ values via environment variables or interactive prompt
  - never echo the API key value to stdout/stderr
  - fail with cause/context/recovery if Vault is unreachable or token missing
  - be usable from inside a dev container (docker-based vault access)

## Security Requirements
- No secrets committed to git.
- No secret values logged.
- Root token usage limited to bootstrap/admin scripts only.
- Runtime services continue using AppRole-scoped policies only.

## Acceptance Criteria
1. Running `./scripts/bootstrap_gofr_dig.sh --yes` results in both AppRole creds files present.
2. Running `./lib/gofr-common/scripts/bootstrap_seq.sh` (or chosen location) successfully writes SEQ secrets into Vault.
3. After SEQ secrets are written, `./docker/start-prod.sh` reports `Logging sink: SEQ configured via Vault AppRole`.
4. Full test suite passes: `./scripts/run_tests.sh`.

## Open Questions (need confirmation)
1. Script location for `bootstrap_seq.sh`:
  - Confirmed: `lib/gofr-common/scripts/bootstrap_seq.sh` (shared across GOFR projects)
2. Input method for SEQ values:
  - Confirmed: use env vars if set; prompt if not; when prompted, export vars for remainder of script execution.
  - Security constraint: never echo API key value.
3. Should `bootstrap_gofr_dig.sh` always run `setup_approle.py`, or only when creds are missing?
  - Confirmed: idempotent, only run when required artifacts are missing.

