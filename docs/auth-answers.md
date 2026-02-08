ANSWERS FOR GOFR-DIG AUTH PATTERN QUESTIONS
============================================

1. BIND MOUNT PATH RESOLUTION FOR vault_creds
---------------------------------------------

The path is resolved using the HOST_PROJECT_ROOT environment variable. In start-prod.sh (lines 53-63):

if [ -f /.dockerenv ]; then
    # Inside dev container - need to find the HOST path
    HOST_PROJECT_ROOT=$(docker inspect gofr-iq-dev --format='{{range .Mounts}}{{if eq .Destination "/home/gofr/devroot/gofr-iq"}}{{.Source}}{{end}}{{end}}' 2>/dev/null)
else
    # On host directly
    HOST_PROJECT_ROOT="$PROJECT_ROOT"
fi
export HOST_PROJECT_ROOT

Key insight: When running inside a dev container, we can't use relative paths because the container's filesystem differs from the host's. We use docker inspect to query the dev container's mount source to find the actual HOST path.


2. EXACT compose.prod.yml VOLUME MOUNT SYNTAX
---------------------------------------------

From docker-compose.yml line 140:

volumes:
  - gofr-iq-data:/home/gofr-iq/data
  - gofr-iq-prod-logs:/home/gofr-iq/logs
  # AppRole credentials (Zero-Trust Bootstrap)
  - ${HOST_PROJECT_ROOT:-..}/lib/gofr-common/secrets/service_creds/gofr-mcp.json:/run/secrets/vault_creds:ro

- Uses HOST_PROJECT_ROOT env var (set by start-prod.sh)
- Falls back to .. if not set (won't work from dev container)
- Mounts the service-specific JSON file to /run/secrets/vault_creds:ro
- Each service gets its own creds file (gofr-mcp.json, gofr-web.json, etc.)


3. hvac DEPENDENCY LOCATION
---------------------------

Both locations have it:

- pyproject.toml (gofr-iq) line 18: "hvac==2.4.0" - direct dependency
- lib/gofr-common/pyproject.toml line 28: "hvac==2.4.0" - shared library

gofr-iq installs gofr-common as an editable dependency, so hvac gets installed via gofr-common. The duplicate in gofr-iq's pyproject.toml is probably redundant but harmless.


4. VAULTIDENTITY FALLBACK BEHAVIOR
----------------------------------

From identity.py and factory.py:

# Factory checks if creds file exists
if VaultIdentity.is_available():
    # Use AppRole auth with auto-renewal
    identity = VaultIdentity(vault_addr=os.environ.get(f"{env_prefix}_VAULT_URL"))
    identity.login()
    identity.start_renewal()
    vault_client = identity.get_client()
else:
    # Fall back to env-based config (token or AppRole via env vars)
    vault_config = VaultConfig.from_env(prefix)
    vault_client = VaultClient(vault_config, logger=logger)

Fallback priority (from gofr_env.py lines 29-31):
1. AppRole (if /run/secrets/vault_creds exists) - Container runtime
2. Root Token from secrets/vault_root_token - Dev/Bootstrap
3. Environment VAULT_TOKEN - Legacy fallback

VaultIdentity.is_available() simply checks: Path(creds_path).exists()


5. AUTH BACKEND DEFAULT VALUE
-----------------------------

From docker-compose.yml line 116:

environment:
  - GOFR_AUTH_BACKEND=vault

The default is "vault". This is hardcoded in the compose file, not using a fallback like ${GOFR_AUTH_BACKEND:-file}.


6. setup_approle.py EXECUTION CONTEXT
-------------------------------------

From start-prod.sh line 340:

uv run scripts/setup_approle.py

Execution context:
- Runs INSIDE the dev container (start-prod.sh checks [ -f /.dockerenv ] at line 53)
- Uses uv run to ensure correct Python environment
- Runs AFTER Vault is started and unsealed (Step 4)
- Runs BEFORE docker-compose up (Step 7)

What it does: Creates AppRole roles in Vault and writes credentials to lib/gofr-common/secrets/service_creds/*.json. These files are then bind-mounted into production containers.


SUMMARY DIAGRAM
---------------

[Dev Container / Host]
  |
  +-- start-prod.sh
        |
        +-- Detects HOST_PROJECT_ROOT (docker inspect if in dev container)
        +-- Starts Vault container
        +-- uv run scripts/setup_approle.py  # Creates AppRole creds
              |
              +-- Writes: lib/gofr-common/secrets/service_creds/gofr-mcp.json
              +-- Writes: lib/gofr-common/secrets/service_creds/gofr-web.json
        |
        +-- docker compose up
              |
              +-- Mounts: ${HOST_PROJECT_ROOT}/lib/gofr-common/secrets/service_creds/gofr-mcp.json
              |           -> /run/secrets/vault_creds (inside container)
              |
              +-- Container starts, VaultIdentity.is_available() returns True
              +-- VaultIdentity loads creds, logs in, starts renewal thread
