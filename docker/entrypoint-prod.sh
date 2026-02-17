#!/bin/bash
# =============================================================================
# gofr-dig Production Entrypoint
# Common startup for all gofr-dig containers: copies AppRole creds, sets up
# directories, then exec's CMD.
#
# JWT signing secret is read from Vault at runtime by JwtSecretProvider.
# No GOFR_JWT_SECRET env var is required.
#
# Usage in compose.prod.yml:
#   entrypoint: ["/home/gofr-dig/entrypoint-prod.sh"]
#   command: ["/home/gofr-dig/.venv/bin/python", "-m", "app.main_mcp", ...]
#
# Environment variables:
#   GOFR_DIG_VAULT_URL    - Vault address (default: http://gofr-vault:<GOFR_VAULT_PORT>)
#   GOFR_DIG_DATA_DIR     - Data root (default: /home/gofr-dig/data)
#   GOFR_DIG_STORAGE_DIR  - Storage dir (default: /home/gofr-dig/data/storage)
#   GOFR_DIG_NO_AUTH      - Set to "1" to disable authentication
# =============================================================================
set -e

VENV_PATH="/home/gofr-dig/.venv"
CREDS_SOURCE="/run/gofr-secrets/service_creds/gofr-dig.json"
CREDS_TARGET="/run/secrets/vault_creds"

# --- Directories -------------------------------------------------------------
DATA_DIR="${GOFR_DIG_DATA_DIR:-/home/gofr-dig/data}"
STORAGE_DIR="${GOFR_DIG_STORAGE_DIR:-/home/gofr-dig/data/storage}"
mkdir -p "${DATA_DIR}" "${STORAGE_DIR}" /home/gofr-dig/logs
chown -R gofr-dig:gofr-dig /home/gofr-dig/data /home/gofr-dig/logs 2>/dev/null || true

# --- Copy AppRole credentials ------------------------------------------------
mkdir -p /run/secrets
if [ -f "${CREDS_SOURCE}" ]; then
    cp "${CREDS_SOURCE}" "${CREDS_TARGET}"
    chown gofr-dig:gofr-dig "${CREDS_TARGET}"
else
    echo "WARNING: No AppRole credentials at ${CREDS_SOURCE}"
fi

# --- Auth flag ---------------------------------------------------------------
EXTRA_ARGS=""
if [ "${GOFR_DIG_NO_AUTH:-}" = "1" ]; then
    echo "WARNING: Authentication is DISABLED (GOFR_DIG_NO_AUTH=1)"
    EXTRA_ARGS="--no-auth"
fi

# --- Exec the service command ------------------------------------------------
# Drop to gofr-dig user and exec the CMD passed by compose
exec su -s /bin/bash gofr-dig -c "exec $* ${EXTRA_ARGS}"
