#!/bin/bash
# =============================================================================
# Migrate secrets into Docker volumes
# =============================================================================
# Copies runtime AppRole credentials into the shared gofr-secrets and
# gofr-secrets-test Docker volumes.
#
# IMPORTANT (Phase 1 hardening):
# - These volumes are mounted into production containers.
# - Do NOT copy Vault bootstrap artifacts (root token, unseal key, init output)
#   into these volumes.
# - Only copy runtime material required by services: service_creds/*.json.
#
# These volumes are SHARED across all GOFR projects.
#
# Run once from the host (or dev container with Docker socket access):
#   ./scripts/migrate_secrets_to_volume.sh
#
# Safe to re-run -- overwrites volume contents with latest from source dir.
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_DIR=""
PROJECT_SECRETS_DIR="$PROJECT_ROOT/secrets"
COMMON_SECRETS_DIR="$PROJECT_ROOT/lib/gofr-common/secrets"
PROJECT_CREDS_DIR="$PROJECT_ROOT/secrets/service_creds"

# Both volumes to seed (shared across all GOFR projects)
VOLUMES=("gofr-secrets" "gofr-secrets-test")

# ---- Helpers ----------------------------------------------------------------
info()  { echo "[INFO]  $*"; }
ok()    { echo "[OK]    $*"; }
err()   { echo "[FAIL]  $*" >&2; }

# ---- Select and verify source creds dir -------------------------------------
# Prefer gofr-common as the base (stable location for shared service_creds),
# then overlay project-local creds (newly provisioned AppRole IDs for gofr-dig).
if [ -d "$COMMON_SECRETS_DIR/service_creds" ]; then
    SOURCE_DIR="$COMMON_SECRETS_DIR"
elif [ -d "$PROJECT_SECRETS_DIR/service_creds" ]; then
    SOURCE_DIR="$PROJECT_SECRETS_DIR"
fi

if [ -z "$SOURCE_DIR" ]; then
    err "Source service_creds not found"
    echo "  Tried:"
    echo "    - $COMMON_SECRETS_DIR/service_creds"
    echo "    - $PROJECT_SECRETS_DIR/service_creds"
    echo "  Expected: service_creds/*.json"
    exit 1
fi

# Build a staging directory that contains ONLY runtime credentials.
# Overlay project-local creds on top of gofr-common service_creds.
TMP_SECRETS_DIR=""
cleanup_tmp() {
    if [ -n "${TMP_SECRETS_DIR:-}" ] && [ -d "${TMP_SECRETS_DIR}" ]; then
        rm -rf "${TMP_SECRETS_DIR}" || true
    fi
}
trap cleanup_tmp EXIT

TMP_SECRETS_DIR="$(mktemp -d)"
mkdir -p "$TMP_SECRETS_DIR/service_creds"

if [ -d "$SOURCE_DIR/service_creds" ]; then
    cp -a "$SOURCE_DIR/service_creds/." "$TMP_SECRETS_DIR/service_creds/"
fi

if [ -d "$PROJECT_CREDS_DIR" ]; then
    cp -a "$PROJECT_CREDS_DIR/." "$TMP_SECRETS_DIR/service_creds/"
fi

info "Source directory: $SOURCE_DIR (service_creds only)"
info "Staging directory: $TMP_SECRETS_DIR"
echo "  Contents:"
ls -la "$TMP_SECRETS_DIR/" | sed 's/^/    /'
echo ""

# ---- Validate JSON structure before seeding ---------------------------------
VALIDATION_FAILED=false
for creds_json in "$TMP_SECRETS_DIR"/service_creds/*.json; do
    [ -f "$creds_json" ] || continue
    basename_json="$(basename "$creds_json")"
    if ! python3 -c "
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as f:
    d = json.load(f)
rid = str(d.get('role_id', '')).strip()
sid = str(d.get('secret_id', '')).strip()
if not rid or not sid:
    raise SystemExit(1)
" "$creds_json" 2>/dev/null; then
        err "Invalid JSON or missing role_id/secret_id in $basename_json"
        VALIDATION_FAILED=true
    else
        ok "Validated $basename_json"
    fi
done

if [ "$VALIDATION_FAILED" = true ]; then
    err "One or more service_creds JSON files failed validation -- aborting."
    exit 1
fi

# ---- Seed each volume -------------------------------------------------------
for VOLUME in "${VOLUMES[@]}"; do
    # Ensure volume exists
    if ! docker volume inspect "$VOLUME" >/dev/null 2>&1; then
        info "Creating volume: $VOLUME"
        docker volume create "$VOLUME"
    fi

    info "Copying secrets into volume $VOLUME ..."

    # Start a disposable Alpine container with the volume mounted
    HELPER="gofr-secrets-migrate-$$"
    docker run -d --name "$HELPER" -v "$VOLUME:/dst" alpine:3.19 sleep 60 >/dev/null

    # IMPORTANT: remove any previous contents so stale bootstrap artifacts do
    # not linger in the runtime volume.
    docker exec "$HELPER" sh -c 'rm -rf /dst/*' >/dev/null 2>&1 || true

    # Copy from the calling container's filesystem into the helper
    docker cp "$TMP_SECRETS_DIR/." "$HELPER:/dst/"

    # Fix permissions inside the volume
    # All GOFR containers use UID 1000 / GID 1000
    docker exec "$HELPER" sh -c '
        chown -R 1000:1000 /dst
        chmod 700 /dst
        chmod 600 /dst/service_creds/*.json 2>/dev/null || true
        echo "  Contents of volume:"
        ls -la /dst/ | sed "s/^/    /"
        if [ -d /dst/service_creds ]; then
            echo "  Service creds:"
            ls -la /dst/service_creds/ | sed "s/^/    /"
        fi
    '

    docker rm -f "$HELPER" >/dev/null 2>&1

    ok "Volume '$VOLUME' seeded successfully."
    echo ""
done

ok "Both volumes seeded. Verify with:"
echo "  docker run --rm -v gofr-secrets:/s:ro alpine ls -la /s/"
echo "  docker run --rm -v gofr-secrets-test:/s:ro alpine ls -la /s/"
