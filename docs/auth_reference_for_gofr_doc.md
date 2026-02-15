# gofr-common/auth — Current Usage Reference (gofr-dig)

Purpose: concise reference for an LLM upgrading gofr-doc to the current gofr-common/auth API.
Compare every section against gofr-doc's current code; any deviation is an upgrade target.

---

## 1. Imports Used by gofr-dig

```python
from gofr_common.auth import AuthService, GroupRegistry, create_stores_from_env
from gofr_common.auth.config import resolve_auth_config
from gofr_common.auth.exceptions import AuthError
from gofr_common.storage.exceptions import PermissionDeniedError
```

Only these are needed for a consumer project. Everything else lives inside gofr-common.

---

## 2. Initialization Sequence (Startup)

Both MCP and web entry points follow the same three-step pattern:

```python
# Step 1 — resolve JWT secret (CLI arg → env var → auto-gen dev secret)
jwt_secret, require_auth = resolve_auth_config(
    env_prefix="GOFR_DIG",       # → reads GOFR_DIG_JWT_SECRET, GOFR_DIG_ENV
    jwt_secret_arg=args.jwt_secret,
    require_auth=not args.no_auth,
    logger=startup_logger,
)

# Step 2 — create Vault-backed token + group stores
token_store, group_store = create_stores_from_env(prefix="GOFR_DIG")
group_registry = GroupRegistry(store=group_store)

# Step 3 — create the AuthService
auth_service = AuthService(
    token_store=token_store,
    group_registry=group_registry,
    secret_key=jwt_secret,
    env_prefix="GOFR_DIG",
    audience="gofr-api",          # ← optional JWT "aud" claim
)
```

If `require_auth` is False (--no-auth or env), `auth_service` is set to `None` and all auth checks become no-ops.

---

## 3. Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `{PREFIX}_JWT_SECRET` | Shared JWT signing key | auto-generated in dev; **required** in prod |
| `{PREFIX}_NO_AUTH` | Set `1` to disable auth entirely | unset (auth enabled) |
| `{PREFIX}_AUTH_BACKEND` | Storage backend | must be `vault` |
| `{PREFIX}_VAULT_URL` | Vault server URL | — |
| `{PREFIX}_VAULT_TOKEN` | Vault token (fallback if no AppRole) | — |
| `{PREFIX}_VAULT_ROLE_ID` | AppRole role ID (preferred over token) | — |
| `{PREFIX}_VAULT_SECRET_ID` | AppRole secret ID | — |
| `{PREFIX}_VAULT_MOUNT_POINT` | KV mount point | `secret` |
| `{PREFIX}_VAULT_PATH_PREFIX` | Path prefix inside KV | `{prefix}/auth` |
| `{PREFIX}_ENV` | `PROD`/`PRODUCTION` blocks auto-gen secrets | — |

Replace `{PREFIX}` with your project prefix (e.g., `GOFR_DOC`).

---

## 4. Token Format (JWT Claims)

Created by `AuthService.create_token()`. Signed with HS256.

```json
{
  "jti": "<uuid>",          // token ID — links to TokenRecord in Vault store
  "groups": ["group-name"], // list of group names
  "iat": 1234567890,        // issued-at (unix timestamp)
  "exp": 1234567890,        // expiry (unix timestamp)
  "nbf": 1234567890,        // not-before (unix timestamp)
  "aud": "gofr-api",        // audience (optional, validated if present)
  "fp":  "fingerprint"      // device fingerprint (optional)
}
```

---

## 5. Token Verification Flow

`AuthService.verify_token(token_str) → TokenInfo`

1. Decode JWT with HS256, verify `exp`, `nbf`, `iat`.
2. Require `jti` claim (token UUID) and `groups` claim.
3. If `aud` claim present in token, validate it matches `self.audience`.
4. If `fp` claim present and caller provides fingerprint, compare them.
5. Look up `jti` in Vault `TokenStore` — token must exist and have `status == "active"`.
6. Verify groups in JWT match groups in stored `TokenRecord`.
7. Return `TokenInfo(token, groups, expires_at, issued_at)`.

Raises `AuthError` (or subclass) on any failure. The caller catches `AuthError`.

### TokenInfo Dataclass

```python
@dataclass
class TokenInfo:
    token: str
    groups: list[str]
    expires_at: datetime | None
    issued_at: datetime
    # Methods: has_group(name), has_any_group(names), has_all_groups(names)
```

---

## 6. Auth Surface A — MCP Tools (tool parameter)

Token is passed as a tool argument, not an HTTP header.

### Schema

Every tool (except `ping`) includes this in its `inputSchema.properties`:

```python
AUTH_TOKEN_SCHEMA = {
    "auth_token": {
        "type": "string",
        "description": "JWT token for authentication. The server verifies "
                       "the token and uses the first group to scope session "
                       "access. Omit for anonymous/public access.",
    }
}
```

### Resolution Function

```python
def _resolve_group_from_token(auth_token: str | None) -> str | None:
    if auth_service is None:        # auth disabled (--no-auth)
        return None
    if not auth_token:              # anonymous / public
        return None
    raw_token = auth_token
    if raw_token.startswith("Bearer "):
        raw_token = raw_token[7:]   # strip prefix if present
    token_info = auth_service.verify_token(raw_token)   # raises AuthError
    return token_info.groups[0] if token_info.groups else None
```

### Handler Pattern

```python
auth_token = arguments.get("auth_token")
try:
    group = _resolve_group_from_token(auth_token)
except AuthError as e:
    return _error_response("AUTH_ERROR", str(e))
# ... use group to scope session operations ...
try:
    result = manager.some_operation(..., group=group)
except PermissionDeniedError as e:
    return _error_response("PERMISSION_DENIED", str(e))
```

---

## 7. Auth Surface B — REST/Web (HTTP header)

Token is passed as a standard Authorization header.

### Resolution Function

```python
def _resolve_group(self, request: Request) -> str | None:
    if self.auth_service is None:
        return None
    auth_header = request.headers.get("authorization", "")
    raw = auth_header
    if raw.startswith("Bearer ") or raw.startswith("bearer "):
        raw = raw[7:]
    if not raw:
        return None
    token_info = self.auth_service.verify_token(raw)
    return token_info.groups[0] if token_info.groups else None
```

### Error Responses

| Error Type | HTTP Status | Error Code |
|---|---|---|
| `AuthError` (invalid/expired/revoked token) | 401 | `AUTH_ERROR` |
| `PermissionDeniedError` (group mismatch on resource) | 403 | `PERMISSION_DENIED` |

---

## 8. Group Scoping

- The **first group** in `token_info.groups` is treated as the primary group.
- This group is passed to session operations (`create_session(group=...)`, `get_session_info(session_id, group=...)`).
- Sessions are stored under their group directory. Access to a session requires membership in the session's group.
- If `group` is `None` (anonymous/no-auth), sessions go into a default/public scope.

---

## 9. Exception Hierarchy

```
AuthError (401)                        ← catch this at the handler level
├── TokenError (401)
│   ├── TokenNotFoundError (401)       — jti not in Vault store
│   ├── TokenRevokedError (401)        — token.status == "revoked"
│   ├── TokenExpiredError (401)        — JWT exp in the past
│   └── TokenValidationError (401)     — bad claims, groups mismatch
├── GroupError (403)
│   ├── InvalidGroupError (403)        — group doesn't exist or is defunct
│   ├── GroupNotFoundError (403)
│   └── GroupAccessDeniedError (403)
└── AuthenticationError (401)
    └── FingerprintMismatchError (401) — device fingerprint mismatch
```

`PermissionDeniedError` is from `gofr_common.storage.exceptions`, not the auth module.

---

## 10. Vault Identity (AppRole Auto-login)

`create_stores_from_env` prefers `VaultIdentity` (reads credentials from `/run/secrets/vault_creds`) over raw env-var token auth. If `VaultIdentity.is_available()`:
1. Authenticates via AppRole.
2. Starts background token renewal (AppRole tokens have ~1h TTL).
3. Constructs a `VaultClient` from the authenticated identity.

Fallback: `VaultConfig.from_env(prefix)` reads `{PREFIX}_VAULT_TOKEN` / role_id+secret_id from env.

---

## 11. MCPO Proxy Auth

The MCPO wrapper passes the JWT to the upstream MCP server via HTTP header:

```
--header '{"Authorization": "Bearer <token>"}'
```

Token comes from `{PREFIX}_JWT_TOKEN` env var.

---

## 12. Quick Upgrade Checklist for gofr-doc

1. Does your init sequence match Section 2 exactly (resolve_auth_config → create_stores_from_env → GroupRegistry → AuthService)?
2. Are you using `create_stores_from_env` (with VaultIdentity support), or an older manual VaultConfig setup?
3. Does your `verify_token` call come from `AuthService` (not a lower-level function)?
4. Does the returned object have `token_info.groups` (list), not a single group string?
5. Are you catching `AuthError` (base class) or individual subclasses?
6. Are you using group scoping on storage operations (`group=` parameter)?
7. Does your JWT contain `jti`, `nbf`, `aud` claims? Older versions may only have `iat` + `exp`.
8. Is your Vault path prefix set correctly for your project (`{prefix}/auth`)?
9. Are you using VaultIdentity with AppRole + auto-renewal, or static tokens?
10. Error responses: do you map AuthError → 401 and PermissionDeniedError → 403?
