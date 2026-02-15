# GOFR Auth Alignment Checklist (for other projects)

Purpose: copy/paste-ready checklist to align any GOFR project with the current hardened gofr-dig auth model.

## Required Invariants (must all be true)

1. JWT source of truth is Vault only.
   - Read JWT from `secret/gofr/config/jwt-signing-secret`.
   - Do not source JWT from local `.env` for runtime/admin auth control paths.

2. Runtime roles are least-privilege.
   - Runtime service roles can read shared config/JWT paths as needed.
   - Runtime service roles cannot write `secret/data/gofr/auth/*`.

3. Admin control is isolated.
   - Create a dedicated admin AppRole (e.g., `gofr-admin-control`).
   - Attach dedicated admin policy (e.g., `gofr-admin-control-policy`).
   - Only admin role can mutate auth domain paths.

4. Hard cutover behavior is fail-closed.
   - Auth admin wrappers/scripts require admin role credentials file.
   - Missing/invalid creds must fail with cause + context + recovery guidance.
   - No fallback to runtime roles for auth mutation.

5. Optional elevated bootstrap tasks are explicit.
   - If policy/JWT write operations are optional during bootstrap, gate via explicit flags.
   - Default wrapper behavior should avoid noisy expected permission warnings under scoped admin role.

## Expected Vault Policy Split

- Runtime config-read policy:
  - `read` on `secret/data/gofr/config/*`
- Admin auth policy:
  - `create, read, update, delete, list` on `secret/data/gofr/auth/*`
  - `list, read` on `secret/metadata/gofr/auth/*`

## Required Artifacts

- Admin role credentials file:
  - `secrets/service_creds/gofr-admin-control.json` (or project-equivalent)
- Runtime role credentials file(s):
  - `secrets/service_creds/<runtime-service>.json`

## Wrapper Behavior Contract

Auth/admin wrappers should perform this sequence:

1. Resolve admin creds JSON from secrets path.
2. Parse `role_id` + `secret_id`.
3. AppRole login to Vault to obtain client token.
4. Resolve JWT from Vault path (`secret/gofr/config/jwt-signing-secret`).
5. Execute admin operation.

If any step fails, output:
- Cause (what failed)
- Context (role/path/url/file)
- Recovery (exact next command)

## Quick Validation Commands (adapt names per project)

1. Provision policies + roles + creds:
   - `uv run scripts/setup_approle.py`

2. Validate admin wrapper auth path:
   - `./lib/gofr-common/scripts/auth_manager.sh --docker groups list`

3. Validate bootstrap under scoped admin role:
   - `./lib/gofr-common/scripts/bootstrap_auth.sh --docker --groups-only`

4. Validate full project test suite:
   - `./scripts/run_tests.sh`

## Bootstrap Noise-Suppression Flags (recommended)

When admin role is intentionally scoped and should not perform broad policy/JWT writes:

- `GOFR_BOOTSTRAP_INSTALL_POLICIES=false`
- `GOFR_BOOTSTRAP_STORE_JWT_SECRET=false`

## Non-Goals

- Do not add runtime fallback write permissions “temporarily”.
- Do not widen runtime role to unblock admin workflows.
- Do not move JWT trust source back to `.env` files.

## Reference (implemented baseline)

Detailed implemented baseline and rationale:
- `docs/archive/auth_upgrade_spec.md` (Section “GOFR-DIG Reference State (Implemented, Feb 2026)”)
