# JWT Secret Provider -- Implementation Plan

Reference: docs/jwt_secret_provider_spec.md (all assumptions confirmed)

## Baseline

Run full test suite before starting:

    ./scripts/run_tests.sh

Record pass/fail count for comparison at the end.

---

## Steps

This plan upgrades gofr-dig to the new Vault-backed JWT secret pattern already
implemented in gofr-doc:

- AuthService/TokenService take secret_provider=JwtSecretProvider, not secret_key.
- No GOFR_JWT_SECRET env var.
- No --jwt-secret CLI flag.
- Vault runs inside the ephemeral compose test stack and is seeded by a
  vault-init one-shot container.

Decisions confirmed:

- gofr-dig/lib/gofr-common: merge gofr-doc's gofr-common commit f33a091 into
  gofr-dig's gofr-common (currently 2f4be46) so both changesets are kept.
- Vault location: move Vault into gofr-dig docker/compose.dev.yml (like gofr-doc).
- Dev/test containers: enable auth by default (remove implicit --no-auth).
- Plan location: keep this document as the execution guide.

Prerequisites / operator notes:

- Use ./scripts/run_tests.sh for all testing.
- Use uv run for python commands.
- Do not introduce localhost-only URLs in code or docs; in Docker mode use
  service hostnames (e.g. gofr-vault-test, gofr-dig-mcp-test).
- ASCII only in code and output.

Repository-specific reality check (gofr-dig as of 2026-02-17):

- gofr-dig currently uses `gofr_common.auth.config.resolve_auth_config()` and
  still supports `--jwt-secret` in app entrypoints.
- gofr-dig `docker/entrypoint-prod.sh` reads JWT from Vault and exports
  `GOFR_JWT_SECRET` for the service.
- gofr-dig `docker/compose.dev.yml` currently includes `GOFR_JWT_SECRET` and
  passes `--jwt-secret` when auth is enabled.
- gofr-dig `scripts/run_tests.sh` currently starts Vault via `docker run` and
  exports `GOFR_JWT_SECRET`.
- gofr-dig does NOT have `app/config_docs.py` (do not plan changes there).

Shared auth architecture (MANDATORY -- read jwt_secret_provider_spec.md
"Shared Auth Architecture" section for full details):

All gofr services share ONE set of groups, ONE set of tokens, and ONE
JWT signing secret. The canonical values are:

- Vault path prefix: gofr/auth (NOT per-service like gofr/doc/auth or
  gofr/dig/auth). All services MUST use this path.
- JWT audience: gofr-api. All services MUST use this audience.
- JWT secret: secret/gofr/config/jwt-signing-secret. Shared by all.

Known diffs vs gofr-doc (to avoid accidental assumptions):

- env_prefix: gofr-dig uses GOFR_DIG (not GOFR_DOC). This affects env
  var names (GOFR_DIG_VAULT_URL, etc.) but NOT the path prefix or
  audience.
- AuthService audience: gofr-dig MUST pass audience="gofr-api".
  This is required because TokenService defaults to
  "{env_prefix.lower()}-api" which would be "gofr_dig-api" (WRONG).
- Vault path prefix: gofr-dig MUST set GOFR_DIG_VAULT_PATH_PREFIX=gofr/auth
  in compose files and scripts. The default derived from env_prefix would
  be "gofr/dig/auth" (WRONG). gofr-doc had this same bug (used
  gofr/doc/auth) and it caused "group not found" errors.

  ENV VAR SIDE-EFFECT WARNING: compose files use the syntax
  ${GOFR_XXX_VAULT_PATH_PREFIX:-gofr/auth} which only applies the
  default when the variable is UNSET. If the dev container's environment
  already has the variable set (e.g. from run-dev.sh or Dockerfile), the
  old value overrides the compose default silently. This is how gofr-doc
  ended up with gofr/doc/auth in prod despite the compose file defaulting
  to gofr/auth.

  To prevent this:
  1. Fix run-dev.sh to pass the correct value BEFORE building the dev
     container (already done for gofr-doc).
  2. After fixing run-dev.sh, REBUILD the dev container so the new value
     takes effect. A running container keeps its original env vars.
  3. If you cannot rebuild immediately, override in the shell before
     running start-prod.sh:
       export GOFR_DIG_VAULT_PATH_PREFIX=gofr/auth
  4. Verify the prod container picked up the correct value:
       docker exec <container> env | grep VAULT_PATH_PREFIX
  5. Never rely on compose defaults alone for critical auth settings when
     the dev container may have stale values baked in. Treat the
     run-dev.sh -e flags as the authoritative source.

- Dev-container networking:
  - In Docker-mode integration tests, use service names on gofr-test-net
    (e.g. http://gofr-dig-web-test:<internal_port>).
  - For URLs printed for a human to open from inside the dev container,
    prefer host.docker.internal:<published_port> over localhost.
- Secrets volume: gofr-dig compose.dev.yml uses an external volume
  gofr-secrets-test for AppRole creds; keep using it unless you change the
  test-secrets provisioning flow.

### Step 1 -- Create JwtSecretProvider class

File: `lib/gofr-common/src/gofr_common/auth/jwt_secret_provider.py`

- Implement `JwtSecretProvider` with:
  - `__init__(self, vault_client, vault_path, cache_ttl_seconds, logger)`
  - `get() -> str` -- returns cached secret or reads from Vault
  - `fingerprint` property -- sha256 of current cached secret
  - `invalidate()` -- clears cache, next `get()` re-reads
- `threading.Lock` protects `_cached_secret` and `_cache_expires_at`
- On cache refresh where fingerprint changes, log at WARNING with old/new
- On Vault read failure, raise (do not swallow)

### Step 2 -- Export from auth package

File: `lib/gofr-common/src/gofr_common/auth/__init__.py`

- Import and add `JwtSecretProvider` to the module and `__all__`

### Step 3 -- Unit tests for JwtSecretProvider

File: `test/auth/test_jwt_secret_provider.py`

- Test: first `get()` reads from Vault
- Test: second `get()` within TTL returns cached (no Vault call)
- Test: `get()` after TTL expires re-reads from Vault
- Test: fingerprint changes logged at WARNING
- Test: `invalidate()` forces re-read
- Test: Vault read failure raises
- Test: thread safety (concurrent `get()` calls)
- Use mock VaultClient (no real Vault needed for unit tests)

### Step 4 -- Replace `secret_key` with `secret_provider` in TokenService

File: `lib/gofr-common/src/gofr_common/auth/token_service.py`

- Replace `secret_key: Optional[str]` parameter with
  `secret_provider: JwtSecretProvider`
- Remove env-var fallback logic and auto-generated secret logic
- Replace all `self._secret_key` reads with `self._secret_provider.get()`
- Update `secret_key` property to call `self._secret_provider.get()`
- Update `secret_fingerprint` property to delegate to provider

### Step 5 -- Replace `secret_key` with `secret_provider` in AuthService

File: `lib/gofr-common/src/gofr_common/auth/service.py`

- Replace `secret_key: Optional[str]` parameter with
  `secret_provider: JwtSecretProvider`
- Pass provider through to `TokenService`
- Update `_secret_fingerprint()` to delegate to provider
- Update docstring examples

### Step 6 -- Update resolve_auth_config

File: `lib/gofr-common/src/gofr_common/auth/config.py`

- Change `resolve_auth_config()` return type from
  `Tuple[Optional[str], bool]` to `Tuple[Optional[JwtSecretProvider], bool]`
- When auth is required: build VaultClient from AppRole creds at
  `/run/secrets/vault_creds` (or env vars for Vault URL/creds),
  construct `JwtSecretProvider`, return it
- Remove `jwt_secret_arg` parameter
- Remove env-var fallback (`GOFR_JWT_SECRET`)
- Remove auto-generated secret logic
- Remove `_fingerprint_secret()` helper (provider handles this)
- Remove `resolve_jwt_secret_for_cli()` entirely

### Step 7 -- Update app/startup/auth_config.py

gofr-dig note: gofr-dig does not have `app/startup/auth_config.py`.
No changes required under `app/startup/` for this migration.

### Step 8 -- Update main_mcp.py

File: `app/main_mcp.py`

- Remove `--jwt-secret` CLI argument
- Update `resolve_auth_config()` call: remove `jwt_secret_arg`
- Change variable name from `jwt_secret` to `secret_provider`
- Pass `secret_provider` to `AuthService` constructor instead of
  `secret_key`

### Step 9 -- Update main_web.py

File: `app/main_web.py`

- Same changes as Step 8 for the web server entry point

### Step 10 -- Update token_manager.py

File: `app/management/token_manager.py`

- Remove `--secret` CLI argument
- Remove `GOFR_JWT_SECRET` env var references
- Build `VaultClient` from AppRole creds (env vars already set by
  `auth_manager.sh`)
- Construct `JwtSecretProvider` directly
- Pass to `AuthService` as `secret_provider`
- Remove import of `resolve_jwt_secret_for_cli`

### Step 11 -- Update entrypoint-prod.sh

File: `docker/entrypoint-prod.sh`

- Remove lines 55-84 (JWT-reading section)
- Remove `GOFR_JWT_SECRET` from header comments
- Keep AppRole credential copying (still needed for the provider)

### Step 12 -- Update compose.dev.yml

File: `docker/compose.dev.yml`

- Remove `GOFR_JWT_SECRET` env var from all service definitions
- Remove `--jwt-secret` from any command strings

### Step 13 -- Update auth_manager.sh

File: `lib/gofr-common/scripts/auth_manager.sh`

- Remove the JWT-reading section (vault_kv_get, JWT_SECRET export)
- Remove `GOFR_JWT_SECRET` from the env export
- Keep AppRole login (still needed -- exports `GOFR_VAULT_TOKEN`,
  `GOFR_VAULT_ROLE_ID`, `GOFR_VAULT_SECRET_ID` for auth_manager.py)

### Step 14 -- Update auth_manager.py

File: `lib/gofr-common/scripts/auth_manager.py`

- Construct `VaultClient` from env vars (`GOFR_VAULT_URL`,
  `GOFR_VAULT_ROLE_ID`, `GOFR_VAULT_SECRET_ID`)
- Construct `JwtSecretProvider` with that client
- Pass to `AuthService` as `secret_provider`
- Remove `GOFR_JWT_SECRET` env var reads

### Step 15 -- (Skip) config_docs.py

gofr-dig note: `app/config_docs.py` does not exist in gofr-dig.

### Step 16 -- Update existing auth tests

Files: `test/auth/`, `test/mcp/`, `test/web/`

- Update any tests that pass `secret_key` to AuthService/TokenService
  to instead pass a `JwtSecretProvider` (using mock VaultClient)
- Update any tests that set `GOFR_JWT_SECRET` env var to use the
  provider pattern instead
- Create a test helper: `make_test_secret_provider(secret="test-key")`
  that returns a provider backed by a mock VaultClient

### Step 17 -- Run full test suite

    ./scripts/run_tests.sh

- All tests must pass
- Compare pass count with baseline from before Step 1

---

## gofr-dig Migration Steps

These steps are written so another LLM can execute them deterministically.
They assume the target repo is gofr-dig at /home/gofr/devroot/gofr-dig.

### Step A0 -- Baseline (gofr-dig)

1) In gofr-dig, run the full test suite to establish baseline:

  ./scripts/run_tests.sh

2) Record pass/fail count and keep the full output.

### Step A1 -- Merge gofr-common changes (JwtSecretProvider) into gofr-dig

Goal: get JwtSecretProvider and the secret_provider API into gofr-dig's
gofr-common, without losing gofr-dig's extra commit (mcp_ping.py).

1) Enter the submodule:

  cd /home/gofr/devroot/gofr-dig/lib/gofr-common

2) Add gofr-doc's gofr-common as a temporary remote and fetch:

  git remote add gofr-doc-common /home/gofr/devroot/gofr-doc/lib/gofr-common || true
  git fetch gofr-doc-common

3) Merge the gofr-doc commit that introduced JwtSecretProvider:

  git merge f33a091

4) Resolve conflicts if any. Expected conflict surface is low because both
   branches diverged from 90bad5a and each added one commit.

5) Run gofr-common unit tests as a quick sanity check (from gofr-dig root):

  cd /home/gofr/devroot/gofr-dig
  ./scripts/run_tests.sh test/code_quality/test_code_quality.py -v

6) Update the parent repo submodule pointer:

  git status
  git add lib/gofr-common

Do not commit yet; keep going until gofr-dig is green end-to-end.

### Step A2 -- Update gofr-dig app entrypoints to provider pattern

Files to change:

- app/main_mcp.py
- app/main_web.py

Edits:

1) Remove the --jwt-secret CLI argument from both entrypoints.

2) Stop importing `resolve_auth_config` from `gofr_common.auth.config`.

3) Import and use the same helpers gofr-doc uses:

- create_vault_client_from_env(prefix, logger=...)
- JwtSecretProvider(vault_client=..., logger=...)
- create_stores_from_env(prefix, vault_client=...)

4) Construct AuthService with:
   - secret_provider=...
   - env_prefix="GOFR_DIG"
   - audience="gofr-api"  (MANDATORY -- see spec "Shared Auth Architecture")

5) Keep the existing --no-auth flag behavior.

6) Set GOFR_DIG_VAULT_PATH_PREFIX=gofr/auth in compose files and dev
   scripts. The default derived from GOFR_DIG would be gofr/dig/auth
   which is WRONG -- all services share gofr/auth.

Acceptance:

- Both services start with auth enabled when --no-auth is not passed.
- No reference to GOFR_JWT_SECRET remains in these files.
- Tokens minted by auth_manager are accepted by gofr-dig services.
- Groups created by auth_manager are visible to gofr-dig services.

### Step A3 -- Remove JWT env-var bootstrap from production entrypoint

File to change:

- docker/entrypoint-prod.sh

Edits:

1) Remove the block that reads JWT secret from Vault and exports GOFR_JWT_SECRET.

2) Update header comments to state:

- JWT signing secret is read from Vault at runtime by JwtSecretProvider.
- No GOFR_JWT_SECRET env var is required.

3) Keep copying AppRole creds to /run/secrets/vault_creds.

Acceptance:

- Entrypoint still supports GOFR_DIG_NO_AUTH -> --no-auth.
- Entrypoint no longer references GOFR_JWT_SECRET.

### Step A4 -- Move Vault into gofr-dig compose.dev.yml and enable auth

File to change:

- docker/compose.dev.yml

Edits (mirror gofr-doc's pattern):

1) Add services:

- vault (hashicorp/vault:1.15.4) in dev mode
- vault-init (hashicorp/vault:1.15.4) that seeds the JWT signing secret

2) Configure vault-init to write:

- secret/gofr/config/jwt-signing-secret value="test-secret-key-for-secure-testing-do-not-use-in-production"

3) Update mcp and web services:

- Remove --no-auth from their commands.
- Remove GOFR_JWT_SECRET env var.
- Add GOFR_DIG_VAULT_URL=http://gofr-vault-test:8200
- Add GOFR_DIG_VAULT_TOKEN=gofr-dev-root-token
- Ensure depends_on waits for vault-init to complete successfully.

4) Keep mcpo depending on mcp health.

Acceptance:

- docker compose -f docker/compose.dev.yml up -d brings up Vault, vault-init,
  and app services.
- App services are healthy and accept authenticated requests.

### Step A5 -- Update gofr-dig scripts/start-test-env.sh output

File to change:

- scripts/start-test-env.sh

Edits:

1) Update the comments and the final summary to reflect:

- Auth enabled (no longer "DISABLED" and no longer uses --no-auth).
- URLs suitable for the dev container (avoid localhost; use host.docker.internal
  for host-published ports, and service names for in-network URLs).

Acceptance:

- Script output accurately reflects the compose stack behavior.

### Step A6 -- Update gofr-dig scripts/run_tests.sh to compose-managed Vault

File to change:

- scripts/run_tests.sh

Edits:

1) Remove export GOFR_JWT_SECRET=... (no env var secret).

2) Change start_vault_test_container()/stop_vault_test_container() to match
   gofr-doc behavior:

- Ensure test network exists and dev container is connected.
- Set GOFR_DIG_VAULT_URL and GOFR_DIG_VAULT_TOKEN based on whether running in
  Docker.
- Do NOT docker run Vault here; Vault is managed by compose.dev.yml.

3) Export the generic env vars used by gofr-common tests:

- GOFR_VAULT_URL=${GOFR_DIG_VAULT_URL}
- GOFR_VAULT_TOKEN=${GOFR_DIG_VAULT_TOKEN}

4) Keep addressing-mode logic (--docker / --no-docker) intact for MCP/Web URLs.

5) Ensure the trap cleanup does not attempt to stop/remove a standalone Vault.

Acceptance:

- ./scripts/run_tests.sh starts services (including Vault) via scripts/start-test-env.sh.
- Vault env vars are set for pytest and integration tests.

### Step A7 -- Update gofr-dig test fixtures to secret_provider

File to change:

- test/conftest.py

Edits:

1) Add a helper equivalent to gofr-doc:

- make_test_secret_provider(secret=TEST_JWT_SECRET) that returns
  JwtSecretProvider backed by a MagicMock VaultClient read_secret returning
  {"value": secret}.

2) Update _create_test_auth_service() to pass:

- secret_provider=make_test_secret_provider()

3) Remove configure_test_auth_environment's GOFR_JWT_SECRET env-var set/unset.
  Keep:

- GOFR_DIG_AUTH_BACKEND=vault
- GOFR_DIG_VAULT_URL / GOFR_DIG_VAULT_TOKEN defaults

4) Update/replace the test_server_manager fixture:

- It currently passes jwt_secret=TEST_JWT_SECRET into ServerManager.
- If ServerManager isn't present (it currently is not found), simplify by
  removing the fixture entirely or adjusting it to the new provider pattern.
  Prefer removing it if unused.

5) If gofr-dig has integration tests that need tokens visible to the running
   servers, add server_auth_service/server_*_headers fixtures like gofr-doc,
   using GOFR_DIG_VAULT_PATH_PREFIX default (currently gofr-dig uses gofr/auth).

Acceptance:

- No tests refer to secret_key= for AuthService.
- No tests set GOFR_JWT_SECRET.

### Step A8 -- Fix compile/type errors and update imports

After Step A1 and Step A2/A7, gofr-dig will likely need import fixes because
AuthService signature changes.

Process:

1) Run:

  ./scripts/run_tests.sh test/code_quality/test_code_quality.py -v

2) Then run:

  ./scripts/run_tests.sh

3) Fix failures iteratively, staying within scope:

- update any AuthService(..., secret_key=...) call sites
- update any TokenService(secret_key=...) call sites if present
- remove GOFR_JWT_SECRET references

### Step A9 -- Verify docker compose stack manually (optional but recommended)

1) Bring up the stack:

  ./scripts/start-test-env.sh --build

2) Confirm containers:

  docker compose -f docker/compose.dev.yml ps

3) Confirm logs for vault-init success:

  docker compose -f docker/compose.dev.yml logs

4) Bring it down:

  ./scripts/start-test-env.sh --down

### Step A10 -- Final acceptance run (gofr-dig)

1) Run the full suite again:

  ./scripts/run_tests.sh

Acceptance:

- Full suite passes.
- No GOFR_JWT_SECRET usage remains.
- No --jwt-secret flag remains.
- Dev/test stack runs with auth enabled and Vault in compose.


---

## Not changed (out of scope)

- `auth_env.sh` -- shell-only, not used by Python services
- Vault secret rotation automation
- Token re-issuance on rotation
