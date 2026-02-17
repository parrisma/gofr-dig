# JWT Secret Provider Spec Compliance Audit

Date: 2026-02-17
Spec: docs/jwt_secret_provider_spec.md

---

## Summary

| # | Item | Verdict |
|---|------|---------|
| 1 | JwtSecretProvider class interface | PASS |
| 2 | AuthService/TokenService use secret_provider | PASS |
| 3 | No GOFR_JWT_SECRET in code files | PARTIAL |
| 4 | No --jwt-secret CLI flag | PASS |
| 5 | entrypoint-prod.sh JWT section removed | PASS |
| 6 | compose.dev.yml clean | PASS |
| 7 | run_tests.sh clean | PASS |
| 8 | Shared Auth Architecture compliance | PASS |
| 9 | Tests use JwtSecretProvider | PARTIAL |
| 10 | start-test-env.sh clean | PASS |
| 11 | start-prod.sh clean | PARTIAL |
| 12 | auth_manager.sh JWT section removed | PASS |
| 13 | resolve_auth_config/resolve_jwt_secret_for_cli removed | PASS |

10 PASS, 3 PARTIAL, 0 FAIL

---

## Detailed Findings

### 1. JwtSecretProvider class interface -- PASS

File: lib/gofr-common/src/gofr_common/auth/jwt_secret_provider.py

All required interface elements present:
- __init__(vault_client, vault_path, cache_ttl_seconds, logger) -- correct
- get() -> str -- correct, reads from Vault with TTL cache
- fingerprint property -- correct, returns sha256:<first 12 hex chars>
- invalidate() -- correct, resets cache expiry
- threading.Lock -- correct, self._lock used in get() and invalidate()
- Default vault_path: "gofr/config/jwt-signing-secret" -- correct
- Default cache_ttl_seconds: 300 -- correct

### 2. AuthService/TokenService use secret_provider -- PASS

- AuthService.__init__ accepts `secret_provider: "JwtSecretProvider"` (no secret_key: str param)
- TokenService.__init__ accepts `secret_provider: "JwtSecretProvider"` (no secret_key: str param)
- Both expose `secret_key` only as a read-only property that calls `self._secret_provider.get()`

### 3. No GOFR_JWT_SECRET in code files -- PARTIAL

Compliant (no references):
- app/** -- clean
- lib/**/*.py -- clean
- docker/compose.dev.yml -- clean
- docker/compose.prod.yml -- clean
- scripts/run_tests.sh -- clean
- scripts/start-test-env.sh -- clean

Non-compliant references found:

1. lib/gofr-common/scripts/auth_env.sh (lines 20, 95-107):
   - Still reads JWT secret from Vault and exports GOFR_JWT_SECRET as a
     shell env var. This is a gofr-common shared script, not a doc file.
   - Line 20: documents "GOFR_JWT_SECRET=..." as output
   - Line 107: `export GOFR_JWT_SECRET=$JWT_SECRET`

2. test/conftest.py (lines 223, 239):
   - `os.environ["GOFR_JWT_SECRET"] = TEST_JWT_SECRET` (set)
   - `os.environ.pop("GOFR_JWT_SECRET", None)` (cleanup)
   - This env var is never actually consumed by any code, making it dead code.

3. .github/copilot-instructions.md (line 139):
   - Documents auth_env.sh as exporting GOFR_JWT_SECRET. Stale documentation.

### 4. No --jwt-secret CLI flag -- PASS

- main_mcp.py: Only --host, --port, --no-auth, --templates-dir, --styles-dir, --web-url, --proxy-url-mode
- main_web.py: Only --host, --port, --no-auth
- No --jwt-secret anywhere in either file.

### 5. entrypoint-prod.sh JWT section removed -- PASS

The entrypoint only:
- Creates directories
- Copies AppRole creds from /run/gofr-secrets/service_creds/gofr-dig.json
- Handles --no-auth flag
- Execs the CMD

Header comment correctly states: "No GOFR_JWT_SECRET env var is required."

### 6. compose.dev.yml clean -- PASS

No GOFR_JWT_SECRET env var or --jwt-secret flag in any service definition.
JWT secret is seeded into Vault by vault-init service at path
secret/gofr/config/jwt-signing-secret, which is the correct pattern.

### 7. run_tests.sh clean -- PASS

Searched all 458 lines. No GOFR_JWT_SECRET export or reference.

### 8. Shared Auth Architecture compliance -- PASS

All three sub-requirements met:

a) GOFR_DIG_VAULT_PATH_PREFIX defaults to gofr/auth (NOT gofr/dig/auth):
   - compose.dev.yml: `GOFR_DIG_VAULT_PATH_PREFIX=${GOFR_DIG_VAULT_PATH_PREFIX:-gofr/auth}` -- correct
   - compose.prod.yml: `GOFR_DIG_VAULT_PATH_PREFIX=${GOFR_DIG_VAULT_PATH_PREFIX:-gofr/auth}` -- correct
   - simulator/core/auth.py: `os.environ.setdefault("GOFR_DIG_VAULT_PATH_PREFIX", "gofr/auth")` -- correct

b) audience="gofr-api" passed to AuthService:
   - main_mcp.py: `audience="gofr-api"` -- correct
   - main_web.py: `audience="gofr-api"` -- correct
   - simulator/core/auth.py: `audience="gofr-api"` -- correct

c) JWT secret path is gofr/config/jwt-signing-secret:
   - JwtSecretProvider default: `vault_path="gofr/config/jwt-signing-secret"` -- correct
   - compose.dev.yml vault-init seeds: `secret/gofr/config/jwt-signing-secret` -- correct

### 9. Tests use JwtSecretProvider -- PARTIAL

Compliant:
- conftest.py provides `make_test_secret_provider()` which creates a
  JwtSecretProvider with a mocked VaultClient
- `_create_test_auth_service()` passes `secret_provider=secret_provider` (JwtSecretProvider)
- No `secret_key=` parameter usage anywhere in test/**
- No `secret_key=` parameter usage anywhere in simulator/**

Gap:
- conftest.py `configure_test_auth_environment()` still sets
  `os.environ["GOFR_JWT_SECRET"]` (line 223) and cleans it up (line 239).
  This env var is never read by any code -- it is dead code left over from
  the migration. Harmless but should be removed for cleanliness.

### 10. start-test-env.sh clean -- PASS

Reviewed all 255 lines. No GOFR_JWT_SECRET reference.

### 11. start-prod.sh -- PARTIAL

No code usage of GOFR_JWT_SECRET, but the header comment block (line 25) reads:

    GOFR_JWT_SECRET env var is only needed as an override (not recommended for prod).

This is a stale/misleading comment. The code never reads or passes GOFR_JWT_SECRET.
The rest of the script correctly uses AppRole auth to fetch SEQ logging secrets
from Vault and does not touch JWT secrets at all.

### 12. auth_manager.sh JWT section removed -- PASS

The script:
- Uses AppRole credentials (gofr-admin-control) to authenticate to Vault
- Does not read, export, or reference GOFR_JWT_SECRET
- Header comment correctly states: "JWT signing secret is read from Vault at
  runtime by JwtSecretProvider in auth_manager.py -- no env var needed."
- Delegates to `auth_manager.py --backend vault` with the AppRole token

### 13. resolve_auth_config() and resolve_jwt_secret_for_cli() removed -- PASS

File: lib/gofr-common/src/gofr_common/auth/config.py

The entire module body has been replaced with a docstring explaining the removal:

    Previously provided resolve_auth_config() for resolving JWT secrets from
    CLI arguments, environment variables, and defaults. These functions have
    been removed -- JWT secrets are now always resolved via JwtSecretProvider
    backed by Vault.

No code references to these functions remain in app/** or lib/**/*.py.
References only exist in docs/archive/ (historical documentation).

---

## Remediation Items (3 PARTIAL findings)

1. Remove `GOFR_JWT_SECRET` export from `lib/gofr-common/scripts/auth_env.sh`.
   The script should either stop reading/exporting the JWT secret entirely
   (since consumers now use JwtSecretProvider), or be updated to note that
   this export is only for legacy/external consumers.

2. Remove dead `GOFR_JWT_SECRET` env var set/cleanup from
   `test/conftest.py` `configure_test_auth_environment()` (lines 223, 239).

3. Fix stale comment in `scripts/start-prod.sh` line 25. Change from
   "GOFR_JWT_SECRET env var is only needed as an override" to something like
   "Vault must be running with the JWT secret. No GOFR_JWT_SECRET env var
   is used."

4. Update `.github/copilot-instructions.md` line 139 to remove the mention
   of GOFR_JWT_SECRET from the auth_env.sh description (contingent on item 1).
