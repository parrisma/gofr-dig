# Implementation Plan: AppRole Provisioning + SEQ Secret Bootstrap

Status: Approved + Completed
Depends on: `docs/approle_and_seq_bootstrap_spec.md`

Execution Log:
- Step 0 baseline: DONE (`./scripts/run_tests.sh` → 506 passed)
- Step 1 AppRole provisioning in bootstrap: DONE
- Step 2 bootstrap_seq.sh added: DONE
- Step 3 docs updated: DONE
- Step 4 targeted validation: DONE (`ensure_approle.sh --check`, bash syntax checks)
- Step 5 acceptance: DONE (`./scripts/run_tests.sh` → 506 passed)

## Step 0 — Baseline
- Run `./scripts/run_tests.sh` and record outcome.

## Step 1 — Update bootstrap to run AppRole provisioning
- Modify `scripts/bootstrap_gofr_dig.sh` to run `uv run scripts/setup_approle.py` after Vault health verification, only when required creds are missing.
- Ensure the step is idempotent and has clear error output.
- Verification:
  - `secrets/service_creds/gofr-dig.json` exists
  - `secrets/service_creds/gofr-admin-control.json` exists

## Step 2 — Add `bootstrap_seq.sh`
- Implement `bootstrap_seq.sh` at `lib/gofr-common/scripts/bootstrap_seq.sh`.
- Behavior:
  - reads SEQ URL and SEQ API key from env if set; prompts if not set
  - when prompted, exports vars for remainder of script execution
  - writes Vault secrets at:
    - `secret/gofr/config/logging/seq-url` field `value`
    - `secret/gofr/config/logging/seq-api-key` field `value`
  - redacts secrets in logs
- Verification:
  - `vault kv get -field=value secret/gofr/config/logging/seq-url` works
  - `vault kv get -field=value secret/gofr/config/logging/seq-api-key` works

## Step 3 — Update docs/runbook
- Update new-machine bootstrap docs to include SEQ seeding step.
- Ensure it’s clear that SEQ secrets are operator-provided and not auto-generated.

## Step 4 — Targeted validation
- Run:
  - `./scripts/bootstrap_gofr_dig.sh --yes`
  - `./lib/gofr-common/scripts/bootstrap_seq.sh` (or chosen location)
  - `./docker/start-prod.sh` and confirm SEQ configured

## Step 5 — Acceptance
- Run full suite: `./scripts/run_tests.sh`.

## Approval Gate
Approved and executed (see Execution Log).
