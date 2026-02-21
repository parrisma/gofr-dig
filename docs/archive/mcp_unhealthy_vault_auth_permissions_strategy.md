# Strategy: Fix `gofr-dig-mcp` Unhealthy (Vault auth-store permission denied)

Date: 2026-02-15

## Symptom
- `./docker/start-prod.sh` starts the stack but `gofr-dig-mcp` restarts/unhealthy.
- Container logs show:
  - `VaultPermissionError: Permission denied: gofr/auth/groups/_index/names`
  - HTTP call denied: `GET /v1/secret/data/gofr/auth/groups/_index/names`

## Hypothesis (most likely)
- The runtime AppRole used by `gofr-dig-mcp` (creds file `secrets/service_creds/gofr-dig.json`) is missing **read/list** access to the auth-store paths under KV:
  - `secret/data/gofr/auth/*`
  - `secret/metadata/gofr/auth/*`
- The service needs read access to auth-store data to initialize `GroupRegistry` and to verify tokens.

## Constraints / Security Invariants
- Do not grant runtime roles write access to `secret/data/gofr/auth/*`.
- Admin operations (create/update/delete auth entries) stay scoped to the admin-control role.

## Diagnostic Steps
1. Confirm the policies attached to the `gofr-dig` AppRole:
   - `vault read auth/approle/role/gofr-dig`
2. Inspect the `gofr-dig` policy document in Vault:
   - `vault policy read <policy-name>`
3. Verify whether that policy contains read/list on `secret/data/gofr/auth/*` and `secret/metadata/gofr/auth/*`.

## Fix Plan
1. Update gofr-common policy definition(s) so runtime policies include auth-store **read/list** only.
2. Re-apply policies and roles via `uv run scripts/setup_approle.py` using a privileged token (root/admin-control), so Vault policy content is updated.
3. Restart the prod stack and confirm `gofr-dig-mcp` is healthy.

## Validation
- `docker logs gofr-dig-mcp` no longer shows `VaultPermissionError`.
- `./docker/start-prod.sh` completes successfully and all services are healthy.
- Optional: run `./scripts/run_tests.sh --unit` to sanity-check auth startup paths.
