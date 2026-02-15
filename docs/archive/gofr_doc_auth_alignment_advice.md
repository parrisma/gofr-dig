# GOFR-DOC Auth Alignment Advice

Audience: engineers/LLM maintainers implementing auth alignment in gofr-doc.

## Recommended Direction

Adopt the same security invariants as gofr-dig, but keep gofr-doc service policy inventory local to gofr-doc.

What to share vs localize:
- Shared in gofr-common:
  - auth library primitives (stores, registry, verification)
  - generic policy building blocks
  - installer/provisioning helpers
- Local in gofr-doc:
  - concrete service policy map and policy names
  - concrete role names
  - wrapper wiring and runbook

## Mandatory Invariants for gofr-doc

1. Vault JWT source of truth only
- JWT must be read from Vault path `secret/gofr/config/jwt-signing-secret`.
- No local `.env` fallback for auth control flows.

2. Runtime roles are read-only for auth domain
- Runtime roles may read shared config/JWT paths as needed.
- Runtime roles must not have write permissions on `secret/data/gofr/auth/*`.

3. Dedicated admin role for auth mutation
- Create a gofr-doc admin control role (for example `gofr-doc-admin-control`).
- Attach dedicated admin policy (for example `gofr-doc-admin-control-policy`).
- Only this role can perform auth CRUD operations.

4. Hard cutover and fail-closed wrappers
- Admin wrappers must require admin AppRole creds JSON.
- If creds are missing/invalid, stop with cause + context + recovery.
- No fallback to runtime role for auth-management commands.

5. Optional elevated bootstrap work must be explicit
- Policy/JWT write steps during bootstrap should be opt-in or explicitly toggled.
- Default operational path should avoid expected permission-denied warning noise.

## Concrete Implementation Plan for gofr-doc

Phase A (fast alignment)
1. Update startup wiring to modern auth API:
   - `resolve_auth_config` new signature
   - `create_stores_from_env(prefix="GOFR_DOC")`
   - `GroupRegistry`
   - `AuthService(token_store, group_registry, secret_key, env_prefix)`
2. Update token usage from `token_info.group` to `token_info.groups`.
3. Replace generic exception parsing with explicit `AuthError` handling.
4. Remove file token-store path arguments and file-backed auth assumptions.

Phase B (policy ownership cleanup)
5. Move gofr-doc concrete policy inventory to gofr-doc repo (not gofr-common).
6. Keep shared installer in gofr-common, but pass gofr-doc policy map from local bootstrap.
7. Introduce admin-control AppRole provisioning by default for gofr-doc.
8. Update wrappers to use admin creds and AppRole login flow.

Phase C (verification)
9. Validate:
   - admin wrapper group/token operations succeed
   - runtime services still read JWT/config successfully
   - runtime cannot write auth domain
10. Run full test suite and capture acceptance evidence.

## Naming Recommendation for gofr-doc

To avoid cross-project collisions, prefer project-scoped names:
- `gofr-doc-runtime-policy` (or runtime policies per service)
- `gofr-doc-admin-control-policy`
- `gofr-doc-admin-control` role

## What Not to Do

- Do not keep project-specific role/policy names in gofr-common long term.
- Do not grant runtime roles temporary auth write access “for migration”.
- Do not reintroduce JWT secrets from local `.env` for operational auth scripts.

## Suggested Handoff Message (copy/paste)

"Align gofr-doc to gofr-dig auth hardening with local policy ownership: Vault JWT source-of-truth, runtime read-only auth domain, dedicated admin-control AppRole for auth mutation, fail-closed wrappers, and explicit toggles for optional elevated bootstrap steps. Implement fast API alignment first, then localize policy inventory out of gofr-common."
