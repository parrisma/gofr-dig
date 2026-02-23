#!/bin/bash
# =============================================================================
# Ensure gofr-dig Vault AppRole credentials + policies are current
# =============================================================================
# Self-healing behavior:
#   - If creds exist: syncs policies & roles without regenerating credentials
#   - If creds missing: full provision (policies + roles + new credentials)
#
# This means policy changes in gofr-common are applied on every
# start-prod.sh / bootstrap_gofr_dig.sh run — no manual reprovision needed.
#
# Designed to be called from start-prod.sh (and safe to call repeatedly).
#
# Exit codes:
#   0 — credentials exist and policies are synced
#   1 — cannot provision (Vault not available, not unsealed, etc.)
#
# Usage:
#   ./scripts/ensure_approle.sh          # Sync policies; provision creds if needed
#   ./scripts/ensure_approle.sh --check  # Check only, don't provision or sync
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Secrets directory — inside the dev container this is the gofr-secrets Docker
# volume (mounted at $PROJECT_ROOT/secrets by run-dev.sh).  On the host it may
# not exist yet, so we fall back to lib/gofr-common/secrets/ where
# manage_vault.sh bootstrap writes the initial credentials.
# Source port config (single source of truth)
_PORTS_ENV="$PROJECT_ROOT/lib/gofr-common/config/gofr_ports.env"
if [ -f "$_PORTS_ENV" ]; then
    # shellcheck source=/dev/null
    source "$_PORTS_ENV"
fi
unset _PORTS_ENV

SECRETS_DIR="$PROJECT_ROOT/secrets"
FALLBACK_SECRETS_DIR="$PROJECT_ROOT/lib/gofr-common/secrets"
CREDS_FILE="$SECRETS_DIR/service_creds/gofr-dig.json"
ADMIN_CREDS_FILE="$SECRETS_DIR/service_creds/gofr-admin-control.json"
FALLBACK_CREDS_FILE="$FALLBACK_SECRETS_DIR/service_creds/gofr-dig.json"
FALLBACK_ADMIN_CREDS_FILE="$FALLBACK_SECRETS_DIR/service_creds/gofr-admin-control.json"
VAULT_CONTAINER="gofr-vault"
VAULT_PORT="${GOFR_VAULT_PORT:?GOFR_VAULT_PORT not set — source gofr_ports.env}"

CHECK_ONLY=false
[ "${1:-}" = "--check" ] && CHECK_ONLY=true

# ---- Helpers ----------------------------------------------------------------
info()  { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
warn()  { echo "[WARN]  $*"; }
err()   { echo "[FAIL]  $*" >&2; }

# ---- Determine mode ---------------------------------------------------------
# Creds exist?  →  sync policies only (self-healing, no cred regen)
# Creds missing →  full provision (policies + roles + new credentials)
CREDS_PRESENT=false
if { [ -f "$CREDS_FILE" ] && [ -f "$ADMIN_CREDS_FILE" ]; } || \
   { [ -f "$FALLBACK_CREDS_FILE" ] && [ -f "$FALLBACK_ADMIN_CREDS_FILE" ]; }; then
    CREDS_PRESENT=true
fi

if [ "$CHECK_ONLY" = true ]; then
    if [ "$CREDS_PRESENT" = true ]; then
        ok "AppRole credentials exist"
        exit 0
    else
        warn "AppRole credentials missing"
        exit 1
    fi
fi

# ---- Vault running? ---------------------------------------------------------
VAULT_URL="http://${VAULT_CONTAINER}:${VAULT_PORT}"
VAULT_STATUS=$(curl -s --connect-timeout 3 --max-time 5 "${VAULT_URL}/v1/sys/health" 2>/dev/null || true)

if [ -z "${VAULT_STATUS}" ]; then
    err "Vault is not reachable at ${VAULT_URL}."
    err "  Start it:  ./lib/gofr-common/scripts/manage_vault.sh start"
    exit 1
fi

# ---- Vault unsealed? --------------------------------------------------------
IS_SEALED=$(echo "${VAULT_STATUS}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sealed', True))" 2>/dev/null || echo "True")

if [ "$IS_SEALED" != "False" ]; then
    err "Vault is sealed."
    err "  Unseal it: ./lib/gofr-common/scripts/manage_vault.sh unseal"
    exit 1
fi

ok "Vault is running and unsealed"

# ---- Root token available? --------------------------------------------------
# Try primary path first ($PROJECT_ROOT/secrets), then fallback to gofr-common
ROOT_TOKEN_FILE=""
if [ -f "$SECRETS_DIR/vault_root_token" ]; then
    ROOT_TOKEN_FILE="$SECRETS_DIR/vault_root_token"
elif [ -f "$FALLBACK_SECRETS_DIR/vault_root_token" ]; then
    ROOT_TOKEN_FILE="$FALLBACK_SECRETS_DIR/vault_root_token"
fi

if [ -z "$ROOT_TOKEN_FILE" ]; then
    err "Vault root token not found at:"
    err "  $SECRETS_DIR/vault_root_token"
    err "  $FALLBACK_SECRETS_DIR/vault_root_token"
    err "  Bootstrap Vault first: ./lib/gofr-common/scripts/manage_vault.sh bootstrap"
    exit 1
fi

VAULT_ROOT_TOKEN=$(cat "$ROOT_TOKEN_FILE")
if [ -z "$VAULT_ROOT_TOKEN" ]; then
    err "Vault root token file is empty: $ROOT_TOKEN_FILE"
    exit 1
fi

ok "Root token found"

# ---- Provision / Sync -------------------------------------------------------
export GOFR_VAULT_URL="http://${VAULT_CONTAINER}:${VAULT_PORT}"
export GOFR_VAULT_TOKEN="$VAULT_ROOT_TOKEN"

cd "$PROJECT_ROOT"

if [ "$CREDS_PRESENT" = true ]; then
    # Validate existing creds actually work against Vault.
    # Important: validate ALL required roles (service + admin-control). If either is stale,
    # we must re-provision; file presence alone is not sufficient.

    validate_creds_file() {
        local creds_path="$1"
        local role_id secret_id login_resp

        if [ ! -f "$creds_path" ]; then
            return 1
        fi

        role_id=$(python3 -c "import json; print(json.load(open('$creds_path'))['role_id'])" 2>/dev/null || true)
        secret_id=$(python3 -c "import json; print(json.load(open('$creds_path'))['secret_id'])" 2>/dev/null || true)
        if [ -z "$role_id" ] || [ -z "$secret_id" ]; then
            return 1
        fi

        login_resp=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST -d "{\"role_id\":\"$role_id\",\"secret_id\":\"$secret_id\"}" \
            "http://${VAULT_CONTAINER}:${VAULT_PORT}/v1/auth/approle/login" 2>/dev/null || echo "000")
        [ "$login_resp" = "200" ]
    }

    CREDS_TO_TEST=""
    ADMIN_CREDS_TO_TEST=""

    if [ -f "$CREDS_FILE" ]; then
        CREDS_TO_TEST="$CREDS_FILE"
    elif [ -f "$FALLBACK_CREDS_FILE" ]; then
        CREDS_TO_TEST="$FALLBACK_CREDS_FILE"
    fi

    if [ -f "$ADMIN_CREDS_FILE" ]; then
        ADMIN_CREDS_TO_TEST="$ADMIN_CREDS_FILE"
    elif [ -f "$FALLBACK_ADMIN_CREDS_FILE" ]; then
        ADMIN_CREDS_TO_TEST="$FALLBACK_ADMIN_CREDS_FILE"
    fi

    if validate_creds_file "$CREDS_TO_TEST" && validate_creds_file "$ADMIN_CREDS_TO_TEST"; then
        info "Existing AppRole credentials validated OK (service + admin-control)"
    else
        warn "One or more existing AppRole credential files are invalid -- will re-provision"
        CREDS_PRESENT=false
        rm -f "$CREDS_FILE" "$ADMIN_CREDS_FILE" "$FALLBACK_CREDS_FILE" "$FALLBACK_ADMIN_CREDS_FILE" 2>/dev/null || true
    fi
fi

if [ "$CREDS_PRESENT" = true ]; then
    # Self-healing: sync policies & roles without regenerating credentials
    info "Syncing Vault policies (credentials already exist)..."
    if ! command -v uv &>/dev/null; then
        err "uv is required but not available on PATH"
        err "Fix: install uv (project standard) and retry"
        exit 1
    fi
    uv run lib/gofr-common/scripts/setup_approle.py \
        --project-root "$PROJECT_ROOT" \
        --config config/gofr_approles.json \
        --policies-only
    ok "Policies synced"
    exit 0
fi

# Full provision — creds are missing
info "Provisioning gofr-dig AppRole (full)..."
if ! command -v uv &>/dev/null; then
    err "uv is required but not available on PATH"
    err "Fix: install uv (project standard) and retry"
    exit 1
fi
uv run lib/gofr-common/scripts/setup_approle.py \
    --project-root "$PROJECT_ROOT" \
    --config config/gofr_approles.json

# ---- Verify -----------------------------------------------------------------
if [ -f "$CREDS_FILE" ] && [ -f "$ADMIN_CREDS_FILE" ]; then
    ok "AppRole credentials provisioned: $CREDS_FILE"
    ok "AppRole credentials provisioned: $ADMIN_CREDS_FILE"
    exit 0
elif [ -f "$FALLBACK_CREDS_FILE" ] && [ -f "$FALLBACK_ADMIN_CREDS_FILE" ]; then
    ok "AppRole credentials provisioned: $FALLBACK_CREDS_FILE"
    ok "AppRole credentials provisioned: $FALLBACK_ADMIN_CREDS_FILE"
    exit 0
else
    err "setup_approle.py ran but one or more credentials files were not created"
    err "Expected both:"
    err "  $CREDS_FILE"
    err "  $ADMIN_CREDS_FILE"
    exit 1
fi
