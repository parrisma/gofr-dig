# JWT Secret Provider -- Specification

## Problem Statement

The JWT signing secret lives in Vault at `secret/gofr/config/jwt-signing-secret`.
Every consumer reads it independently, and long-running services cache it for
the lifetime of their process. If the secret is rotated in Vault, running
services continue to use the stale value until they are restarted, causing
signature mismatches between services and newly minted tokens.

Current consumers and how each gets the secret today:

| Consumer | When | How | Caches |
|---|---|---|---|
| `entrypoint-prod.sh` | Container boot | Inline Python snippet using `VaultClient.read_secret` | Forever (env var for process lifetime) |
| `resolve_auth_config()` | Server startup | Reads `GOFR_JWT_SECRET` env var set by entrypoint | Forever (string passed to `AuthService`) |
| `AuthService` / `TokenService` | Server startup | Receives secret as constructor arg, stores as `_secret_key` | Forever (instance attribute) |
| `auth_manager.sh` | Each invocation | Shell script: AppRole login, `vault kv get` | None (script exits after each run) |
| `auth_env.sh` | Each invocation | Shell script: root token, `vault kv get` | None (emits exports) |
| `token_manager.py` | Each invocation | `resolve_jwt_secret_for_cli` reads env var | None (CLI tool) |

The root cause of the mismatch we observed: the prod container started hours
ago and cached `sha256:e913d61f03a1`, while Vault now holds `sha256:87d76cd701b8`.
All fresh consumers (auth_manager, CLI tools) get the current value, but the
running service is stuck on the old one.

## Proposed Solution

A `JwtSecretProvider` class in `gofr_common.auth` that:

1. Acts as the single accessor for the JWT signing secret across all Python consumers.
2. Always reads from Vault. Vault is the only source of truth -- no env-var
   fallback, no `--jwt-secret` CLI override, no static mode.
3. Caches with a configurable TTL so long-running services periodically re-read.
4. Exposes a simple `.get()` method that returns the current (possibly cached) secret.
5. Logs secret rotations (fingerprint changes) when they happen.
6. Is thread-safe for use inside async/threaded servers.

### Design principle

One path: Vault -> cache -> consumer. No fallback modes, no env-var overrides.
Tests use an ephemeral Vault instance with a test-cycle secret injected, so
every environment -- dev, test, prod -- follows the same code path.

### Interface

```
class JwtSecretProvider:
    """Provides the JWT signing secret with time-based cache refresh from Vault."""

    def __init__(
        self,
        vault_client: VaultClient,
        vault_path: str = "gofr/config/jwt-signing-secret",
        cache_ttl_seconds: int = 300,
        logger: Optional[Logger] = None,
    ) -> None: ...

    def get(self) -> str:
        """Return the current JWT secret. Re-reads from Vault if cache has expired."""

    @property
    def fingerprint(self) -> str:
        """SHA256 fingerprint of the current cached secret."""

    def invalidate(self) -> None:
        """Force next get() to re-read from Vault."""
```

### Integration points

1. **`resolve_auth_config()`** -- instead of returning a plain `str`, it
   returns a `JwtSecretProvider` instance. The provider is constructed with
   a `VaultClient` built from AppRole credentials. The `--jwt-secret` CLI
   flag and `GOFR_JWT_SECRET` env var are removed.

2. **`AuthService` / `TokenService`** -- `secret_key: str` parameter is
   replaced by `secret_provider: JwtSecretProvider`. No backward compat
   shim (not live yet). On every `create_token()` and `verify_token()`
   call, they call `provider.get()` instead of reading `self._secret_key`
   directly.

3. **`auth_manager.py`** -- constructs a provider with a `VaultClient` from
   the AppRole creds that `auth_manager.sh` already provisions. The
   `GOFR_JWT_SECRET` env var is no longer needed in the shell wrapper;
   the Python side reads from Vault directly via the provider.

4. **`entrypoint-prod.sh`** -- the entire JWT-reading section (inline
   Python snippet, `GOFR_JWT_SECRET` export) is removed. The entrypoint
   only needs to make AppRole credentials available at
   `/run/secrets/vault_creds` (which it already does). The server process
   reads from Vault via the provider at runtime.

5. **Tests** -- test fixtures spin up an ephemeral Vault (or use the
   test-env Vault started by `run_tests.sh`) and inject a known test
   secret. Tests construct `JwtSecretProvider` with a `VaultClient`
   pointed at that Vault instance. Same code path as production.

### Cache TTL considerations

- Default: 300 seconds (5 minutes). A secret rotation takes at most 5 minutes
  to propagate to all running services.
- Configurable via constructor arg and/or env var (`GOFR_JWT_SECRET_TTL`).
- Short-lived CLI tools also use the provider with the same TTL. Since they
  exit within seconds, only one Vault read ever happens. Same code path.
- On cache refresh, if the fingerprint changed, log at WARNING level
  with old and new fingerprints.

### Thread safety

- The cached secret and expiry timestamp are protected by `threading.Lock`.
- `.get()` acquires the lock, checks expiry, reads from Vault if needed,
  updates cache, releases lock.
- Vault reads happen inside the lock to prevent thundering herd on expiry.
  This is acceptable because reads are fast (<50ms) and infrequent (every
  TTL seconds).

### Token verification during rotation

When the secret rotates, there is a window where tokens signed with the old
secret are still in circulation. Options:

**Option A -- Single-secret (proposed default):** Only the current secret is
used. Tokens signed with the old secret fail verification. Callers must
re-authenticate. This is the simplest model and matches current behaviour
(a restart has the same effect).

**Option B -- Dual-secret grace period:** The provider keeps the previous
secret for a configurable grace period. `verify_token()` tries the current
secret first, falls back to the previous. More complex but zero-downtime
rotation.

## Confirmed Assumptions

1. **Option A (single-secret).** CONFIRMED. Old tokens fail after rotation.
   Callers re-authenticate. No dual-secret grace period.

2. **5-minute default TTL.** CONFIRMED. Tunable via constructor arg.

3. **Entrypoint stops reading JWT.** CONFIRMED. JWT section of
   `entrypoint-prod.sh` removed. Entrypoint only deploys content,
   copies AppRole creds, and exec's the server.

4. **`--jwt-secret` and `GOFR_JWT_SECRET` removed.** CONFIRMED.
   Vault-only everywhere.

5. **`resolve_auth_config()` return type changes.** CONFIRMED. First
   element becomes `Optional[JwtSecretProvider]`.

6. **`TokenService` replaces `secret_key` with `secret_provider`.**
   CONFIRMED. No backward compat shim needed (not live yet). Clean
   replacement: `secret_key: str` removed, `secret_provider:
   JwtSecretProvider` added.

7. **Module at `gofr_common.auth.jwt_secret_provider`.** CONFIRMED.

8. **auth_manager.sh simplifies.** CONFIRMED. JWT-reading shell code
   removed. Python side reads from Vault directly via provider.

9. **Tests always have Vault.** CONFIRMED. Ephemeral Vault with
   test-cycle secrets injected. Same code path as production.

## Resolved Questions

1. **Rotation callback/hook?** Not for v1. The provider logs fingerprint
   changes at WARNING level. If metrics or cache invalidation are needed
   later, add an `on_rotation` callback parameter.

2. **Health-check method?** Deferred. The provider raises on Vault errors,
   which surfaces through the server's existing error handling. A
   dedicated `is_healthy()` can be added if readiness probes need it.

## Shared Auth Architecture (mandatory for all gofr services)

All gofr services share a single auth plane. The rules below are
non-negotiable and apply to every service (gofr-doc, gofr-dig, and any
future service).

### Ground truths

1. ONE set of auth groups, stored in Vault under `gofr/auth/groups/`.
   All services read from and write to this same path.
2. ONE set of tokens that reference those groups. A token minted for one
   service is valid for every other service.
3. ALL tokens are signed by the same JWT secret
   (`secret/gofr/config/jwt-signing-secret`).
4. The JWT secret is written to Vault once at bootstrap and read by
   auth_manager and every running service via JwtSecretProvider.
5. auth_manager and every service have Vault AppRoles that grant read
   access to both `secret/gofr/config/*` and `secret/gofr/auth/*`.
6. The shared secret is injected at bootstrap and is NOT rotated
   automatically (rotation is a manual operator action).

### Canonical values

| Setting              | Canonical value | Why                                       |
|----------------------|-----------------|-------------------------------------------|
| Vault path prefix    | `gofr/auth`     | Shared groups live here. Not per-service.  |
| JWT audience (`aud`) | `gofr-api`      | Shared tokens must validate everywhere.    |
| JWT secret path      | `gofr/config/jwt-signing-secret` | Single secret for all services. |

### Per-service env_prefix

Each service still uses its own env_prefix for environment variable
lookups (GOFR_DOC_VAULT_URL, GOFR_DIG_VAULT_URL, etc.). However,
two derived defaults are WRONG when env_prefix is not "GOFR":

- `create_stores_from_env()` defaults path prefix to
  `{prefix}/auth` (e.g. `gofr/doc/auth`). Override via
  `{PREFIX}_VAULT_PATH_PREFIX=gofr/auth`.
- `TokenService.__init__()` defaults audience to
  `{env_prefix.lower()}-api` (e.g. `gofr_doc-api`). Override by
  passing `audience="gofr-api"` to AuthService.

Failure to override both causes token audience mismatches and
"group not found" errors because the service looks at a per-service
Vault path instead of the shared one.

### Checklist for adding a new service

1. Set `{PREFIX}_VAULT_PATH_PREFIX=gofr/auth` in compose files and
   dev scripts.
2. Pass `audience="gofr-api"` explicitly to AuthService.
3. Verify tokens minted by auth_manager are accepted by the service.
4. Verify groups created by auth_manager are visible to the service.

## Out of scope

- Automatic secret rotation in Vault (handled by Vault policies/operators).
- Token re-issuance on rotation (callers handle re-auth).
- Changes to auth_env.sh (shell-only, not used by Python services).

## What gets removed

These become dead code once the provider is integrated:

- `GOFR_JWT_SECRET` env var (all references in compose files, entrypoints,
  config_docs, resolve_auth_config)
- `--jwt-secret` CLI flags in main_mcp.py, main_web.py, token_manager.py
- `resolve_jwt_secret_for_cli()` in `gofr_common.auth.config`
- JWT-reading section of `entrypoint-prod.sh` (lines 55-84)
- JWT-reading section of `auth_manager.sh`
- `GOFR_JWT_SECRET` default in `compose.dev.yml`
