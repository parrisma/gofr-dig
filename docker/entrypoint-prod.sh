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
    chmod 600 "${CREDS_TARGET}" 2>/dev/null || true
    chown gofr-dig:gofr-dig "${CREDS_TARGET}" 2>/dev/null || true

    # Validate JSON structure and required keys before booting the service.
    if ! python3 - "${CREDS_TARGET}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

role_id = str(data.get('role_id', '')).strip()
secret_id = str(data.get('secret_id', '')).strip()

if not role_id or not secret_id:
    raise SystemExit(1)
PY
    then
        echo "ERROR: Invalid Vault AppRole creds JSON at ${CREDS_TARGET} (missing role_id/secret_id)"
        exit 1
    fi

    # Optional live validation: if Vault is reachable, ensure login succeeds.
    VAULT_ADDR="http://gofr-vault:${GOFR_VAULT_PORT:-8201}"
    if curl -s --connect-timeout 2 --max-time 2 "${VAULT_ADDR}/v1/sys/health" >/dev/null 2>&1; then
        ROLE_ID="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(str(d.get('role_id','')).strip())" "${CREDS_TARGET}" 2>/dev/null || true)"
        SECRET_ID="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(str(d.get('secret_id','')).strip())" "${CREDS_TARGET}" 2>/dev/null || true)"
        if [ -z "${ROLE_ID}" ] || [ -z "${SECRET_ID}" ]; then
            echo "ERROR: Could not parse required keys from ${CREDS_TARGET}"
            exit 1
        fi

        http_code="$(curl -s -o /dev/null -w "%{http_code}" \
            --connect-timeout 2 --max-time 4 \
            -H 'Content-Type: application/json' \
            -X POST \
            -d "{\"role_id\":\"${ROLE_ID}\",\"secret_id\":\"${SECRET_ID}\"}" \
            "${VAULT_ADDR}/v1/auth/approle/login" || true)"

        if [ "${http_code}" != "200" ]; then
            echo "ERROR: Vault AppRole login failed (HTTP ${http_code}); refusing to start with broken creds"
            exit 1
        fi
    else
        echo "WARNING: Vault unreachable at ${VAULT_ADDR}; skipping live AppRole login validation"
    fi
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
