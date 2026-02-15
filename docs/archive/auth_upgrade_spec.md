# Auth Upgrade Specification — gofr-doc → gofr-common/auth (new API)

Purpose: upgrade gofr-doc's authentication layer to match the gofr-dig pattern
using the current gofr-common/auth API (Vault-backed stores, GroupRegistry,
multi-group tokens).

---

## 1. Current State (what gofr-doc does today)

### 1.1 Initialization (main_mcp.py, main_web.py)

```
app/startup/auth_config.py wraps gofr_common.auth.config.resolve_auth_config
but calls an OLD 3-return-value signature that includes token_store_arg /
token_store_path. The new resolve_auth_config returns (jwt_secret, require_auth)
only — no token_store concept.

AuthService is constructed with:
    AuthService(secret_key=jwt_secret, token_store_path=token_store_path)

This is the OLD constructor. The new AuthService requires:
    AuthService(token_store=..., group_registry=..., secret_key=..., env_prefix=...)
```

### 1.2 Token verification

```
MCP: _verify_auth() calls auth_service.verify_token(token) → token_info.group (singular)
Web: _extract_auth_group() calls auth_service.verify_token(token) → token_info.group (singular)

The new TokenInfo has .groups (list), not .group (singular string).
The gofr-dig pattern uses: token_info.groups[0] if token_info.groups else None
```

### 1.3 Exception handling

```
MCP: catches generic Exception, manually parses error strings for "expired"/"invalid"
Web: catches generic Exception, silently returns None

The gofr-dig pattern catches AuthError (base class) or specific subclasses
(TokenExpiredError, TokenRevokedError, etc.) from gofr_common.auth.exceptions.
```

### 1.4 Token/group storage

```
File-based token store (token_store_path points to a JSON file).
No GroupRegistry. No Vault integration for auth storage.
```

### 1.5 app/auth/__init__.py

```
Re-exports from gofr_common.auth: AuthService, TokenInfo, get_auth_service,
verify_token, optional_verify_token, init_auth_service, set_security_auditor,
get_security_auditor.

Missing from re-exports: GroupRegistry, create_stores_from_env, AuthError,
PermissionDeniedError, RESERVED_GROUPS.
```

### 1.6 MCPO

```
Already passes JWT via Authorization: Bearer header to upstream MCP.
Token sourced from GOFR_DOC_JWT_TOKEN env var. This pattern matches gofr-dig.
```

---

## 2. Target State (what gofr-doc should do after upgrade)

Match the gofr-dig pattern from auth_update.md:

1. Initialization: resolve_auth_config (new 2-return sig) → create_stores_from_env →
   GroupRegistry → AuthService(token_store, group_registry, secret_key, env_prefix).
2. Token verification: token_info.groups (list), use groups[0] as primary group.
3. Exception handling: catch AuthError, PermissionDeniedError explicitly.
4. Storage: Vault-backed TokenStore + GroupStore via create_stores_from_env.
5. app/auth/__init__.py: re-export new API surface.
6. MCP tools: AUTH_TOKEN_SCHEMA in tool input schemas (or keep current HTTP-header approach).
7. Web server: standard Authorization: Bearer pattern, 401/403 mapping.

---

## 3. Gaps Identified

| # | Area | Current (gofr-doc) | Target (gofr-dig pattern) | Impact |
|---|------|--------------------|-----------------------------|--------|
| G1 | resolve_auth_config | Old 3-return-value wrapper with token_store_arg | New 2-return-value: (jwt_secret, require_auth) | Rewrite app/startup/auth_config.py |
| G2 | Store creation | File-based token_store_path | create_stores_from_env(prefix="GOFR_DOC") → Vault-backed | Rewrite startup in main_mcp.py, main_web.py |
| G3 | GroupRegistry | Not used | GroupRegistry(store=group_store) required by AuthService | Add to startup |
| G4 | AuthService constructor | AuthService(secret_key=, token_store_path=) | AuthService(token_store=, group_registry=, secret_key=, env_prefix=) | Change all construction sites |
| G5 | TokenInfo.group vs .groups | .group (singular) | .groups (list), use groups[0] | Change mcp_server.py _verify_auth, web_server.py _extract_auth_group |
| G6 | Exception handling (MCP) | Catches Exception, string-parses error messages | Catches AuthError, uses subclass-specific recovery messages | Rewrite _verify_auth error handling |
| G7 | Exception handling (Web) | Catches Exception, silently returns None | Catches AuthError → 401, PermissionDeniedError → 403 | Rewrite _verify_auth_header, _extract_auth_group |
| G8 | app/auth/__init__.py | Exports old API subset | Export GroupRegistry, create_stores_from_env, AuthError, exception hierarchy | Update re-exports |
| G9 | CLI args | --token-store argument in main_mcp, main_web | Not needed (stores come from Vault env vars) | Remove --token-store arg |
| G10 | app/config.py | get_default_token_store_path() | Not needed with Vault backend | Remove or deprecate |
| G11 | Error mapper | RECOVERY_STRATEGIES missing AUTH_ERROR, PERMISSION_DENIED codes | Add auth error codes to mapper.py | Update mapper |
| G12 | Tests | Test against file-based auth | Test against Vault-backed auth (or mocks) | Update test fixtures |

---

## 4. Assumptions (REQUIRE USER CONFIRMATION)

A1. gofr-doc should use the GOFR_DOC env prefix throughout (e.g., GOFR_DOC_JWT_SECRET,
    GOFR_DOC_AUTH_BACKEND, GOFR_DOC_VAULT_URL, etc.). Confirmed by existing code.

A2. The file-based token store (JSON file) is being REPLACED entirely by Vault-backed
    storage. There is no need for a file-based fallback. Is this correct, or do we need
    a migration path for existing tokens?

A3. The --token-store CLI argument can be removed from main_mcp.py and main_web.py since
    stores are created from Vault env vars. Correct?

A4. gofr-doc should set audience="gofr-api" in the AuthService constructor (same as gofr-dig).
    Or should it use a different audience claim?

A5. The MCP token extraction currently supports BOTH:
    (a) auth_token in tool arguments (backward compat)
    (b) Authorization header via HTTP middleware (get_auth_header_from_context)
    gofr-dig uses approach (a) only with an AUTH_TOKEN_SCHEMA. Should gofr-doc:
    - Keep both approaches (current behavior)?
    - Switch to argument-only like gofr-dig?
    - Switch to header-only (the HTTP middleware approach)?

A6. The web server currently supports both X-Auth-Token (legacy group:token format)
    and Authorization: Bearer. Should the X-Auth-Token legacy format be dropped?

A7. Tests currently use file-based auth fixtures. After the upgrade, tests will need
    either Vault mocks or test-mode Vault. The test runner (run_tests.sh) already manages
    Vault for integration tests. Unit tests should use mocked stores. Correct?

A8. The PermissionDeniedError import should come from gofr_common.storage.exceptions
    (not the auth module). Confirmed from auth_update.md.

---

## 5. Out of Scope

- VaultIdentity / AppRole auto-login setup (infrastructure concern, not code change).
- Token migration (old file-based tokens → Vault). Assumed clean cutover.
- MCPO changes (already passes Bearer header correctly).
- Changes to session storage itself (only the auth layer that gates access).
