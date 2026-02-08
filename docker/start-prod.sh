#!/bin/bash
# =============================================================================
# GOFR-DIG Production Start Script
# =============================================================================
# One-command production deployment using docker compose.
#
# What this does:
#   1. Checks prerequisites (docker, docker compose)
#   2. Builds the production image if it doesn't exist (or with --build)
#   3. Sources centralized port config from gofr_ports.env
#   4. Creates the docker network if missing
#   5. Starts the compose stack (mcp, mcpo, web as separate services)
#   6. Runs health checks to verify services are up
#
# Usage:
#   ./start-prod.sh                     # Start (auto-builds if image missing)
#   ./start-prod.sh --build             # Force rebuild before starting
#   ./start-prod.sh --no-auth           # Start without JWT authentication
#   ./start-prod.sh --port-offset 100   # Shift host ports by N (e.g., 8070→8170)
#   ./start-prod.sh --down              # Stop and remove all services
#
# Required environment (unless --no-auth):
#   GOFR_DIG_JWT_SECRET   JWT signing secret — auto-loaded from Vault if available.
#                         Falls back to env var. Generate: openssl rand -hex 32
#
# Optional environment:
#   GOFR_DIG_AUTH_BACKEND Auth backend: vault (default), file, memory
#   GOFR_DIG_LOG_LEVEL    Log level (default: INFO)
#   GOFR_DIG_TOKEN_STORE  Token store path inside container (file backend only)
#   NEO4J_URI             Neo4j bolt URI     (default: bolt://gofr-neo4j:7687)
#   NEO4J_USER            Neo4j user         (default: neo4j)
#   NEO4J_PASSWORD        Neo4j password
#
# Ports are read from lib/gofr-common/config/gofr_ports.env (single source of truth)
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---- Configuration ----------------------------------------------------------
IMAGE_NAME="gofr-dig-prod:latest"
COMPOSE_FILE="$SCRIPT_DIR/compose.prod.yml"
NETWORK_NAME="gofr-net"
PORTS_ENV="$PROJECT_ROOT/lib/gofr-common/config/gofr_ports.env"

FORCE_BUILD=false
NO_AUTH=false
DO_DOWN=false
PORT_OFFSET=0

# ---- Parse arguments --------------------------------------------------------
while [ $# -gt 0 ]; do
    case "$1" in
        --build)     FORCE_BUILD=true; shift ;;
        --no-auth)   NO_AUTH=true; shift ;;
        --port-offset)
            PORT_OFFSET="$2"
            if ! [[ "$PORT_OFFSET" =~ ^[0-9]+$ ]]; then
                echo "Error: --port-offset requires a numeric value"
                exit 1
            fi
            shift 2
            ;;
        --down)      DO_DOWN=true; shift ;;
        --help|-h)
            sed -n '/^# Usage:/,/^# ====/p' "$0" | head -n -1 | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--build] [--no-auth] [--port-offset N] [--down] [--help]"
            exit 1
            ;;
    esac
done

# ---- Helpers ----------------------------------------------------------------
info()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[1;32m[OK]\033[0m    $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[1;31m[FAIL]\033[0m  $*" >&2; exit 1; }

# ---- Prerequisites ----------------------------------------------------------
echo ""
info "Checking prerequisites..."

if ! command -v docker &>/dev/null; then
    fail "docker is not installed or not on PATH"
fi

if ! docker info &>/dev/null 2>&1; then
    fail "Docker daemon is not running (or current user cannot connect)"
fi

if ! docker compose version &>/dev/null 2>&1; then
    fail "docker compose plugin is not installed (need 'docker compose', not 'docker-compose')"
fi

ok "Docker + Compose available"

# ---- Load centralized port config ------------------------------------------
if [ ! -f "$PORTS_ENV" ]; then
    fail "Port config not found: $PORTS_ENV"
fi
set -a
source "$PORTS_ENV"
set +a

# Apply port offset if specified
if [ "$PORT_OFFSET" -gt 0 ]; then
    # Store original (container) ports
    export GOFR_DIG_MCP_CONTAINER_PORT=$GOFR_DIG_MCP_PORT
    export GOFR_DIG_MCPO_CONTAINER_PORT=$GOFR_DIG_MCPO_PORT
    export GOFR_DIG_WEB_CONTAINER_PORT=$GOFR_DIG_WEB_PORT
    # Calculate host ports with offset
    export GOFR_DIG_MCP_HOST_PORT=$((GOFR_DIG_MCP_PORT + PORT_OFFSET))
    export GOFR_DIG_MCPO_HOST_PORT=$((GOFR_DIG_MCPO_PORT + PORT_OFFSET))
    export GOFR_DIG_WEB_HOST_PORT=$((GOFR_DIG_WEB_PORT + PORT_OFFSET))
    ok "Ports loaded with offset +${PORT_OFFSET} (MCP=${GOFR_DIG_MCP_HOST_PORT}, MCPO=${GOFR_DIG_MCPO_HOST_PORT}, Web=${GOFR_DIG_WEB_HOST_PORT})"
else
    # No offset - host ports = container ports
    export GOFR_DIG_MCP_HOST_PORT=$GOFR_DIG_MCP_PORT
    export GOFR_DIG_MCPO_HOST_PORT=$GOFR_DIG_MCPO_PORT
    export GOFR_DIG_WEB_HOST_PORT=$GOFR_DIG_WEB_PORT
    ok "Ports loaded (MCP=${GOFR_DIG_MCP_PORT}, MCPO=${GOFR_DIG_MCPO_PORT}, Web=${GOFR_DIG_WEB_PORT})"
fi

# ---- Handle --down ----------------------------------------------------------
if [ "$DO_DOWN" = true ]; then
    info "Stopping gofr-dig production stack..."
    docker compose -f "$COMPOSE_FILE" down
    ok "Stack stopped"
    exit 0
fi

# ---- Auth check -------------------------------------------------------------
if [ "$NO_AUTH" = true ]; then
    warn "Running WITHOUT authentication (--no-auth). Not suitable for production!"
    export GOFR_DIG_NO_AUTH=1
    export GOFR_DIG_AUTH_BACKEND=memory
else
    # Try to load JWT secret from Vault if not already set
    if [ -z "${GOFR_DIG_JWT_SECRET:-}" ]; then
        VAULT_ROOT_TOKEN_FILE="$PROJECT_ROOT/secrets/vault_root_token"
        if [ -f "$VAULT_ROOT_TOKEN_FILE" ] && docker ps --format '{{.Names}}' | grep -q '^gofr-vault$'; then
            info "Loading JWT secret from Vault..."
            VAULT_ROOT_TOKEN=$(cat "$VAULT_ROOT_TOKEN_FILE")
            JWT_SECRET=$(docker exec \
                -e VAULT_ADDR=http://127.0.0.1:8201 \
                -e VAULT_TOKEN="$VAULT_ROOT_TOKEN" \
                gofr-vault vault kv get -field=value secret/gofr/config/jwt-signing-secret 2>/dev/null) || true

            if [ -n "$JWT_SECRET" ]; then
                export GOFR_DIG_JWT_SECRET="$JWT_SECRET"
                ok "JWT secret loaded from Vault"
            else
                warn "Could not read JWT secret from Vault (path: secret/gofr/config/jwt-signing-secret)"
                echo ""
                echo "  Options:"
                echo "    1. Bootstrap Vault:  ./lib/gofr-common/scripts/manage_vault.sh bootstrap"
                echo "    2. Set manually:     export GOFR_DIG_JWT_SECRET=\$(openssl rand -hex 32)"
                echo "    3. Run without auth: $0 --no-auth"
                echo ""
                fail "Cannot start without JWT secret"
            fi
        else
            echo ""
            echo "  GOFR_DIG_JWT_SECRET is not set and Vault is not available."
            echo ""
            echo "  Options:"
            echo "    1. Start Vault:      ./lib/gofr-common/scripts/manage_vault.sh bootstrap"
            echo "    2. Set manually:     export GOFR_DIG_JWT_SECRET=\$(openssl rand -hex 32)"
            echo "    3. Run without auth: $0 --no-auth"
            echo ""
            fail "Cannot start without JWT secret"
        fi
    else
        ok "JWT secret set from environment"
    fi

    # Set Vault backend env vars for containers
    export GOFR_DIG_AUTH_BACKEND="${GOFR_DIG_AUTH_BACKEND:-vault}"

    # AppRole credentials are baked into the prod image at /run/secrets/vault_creds
    # (via Dockerfile.prod COPY from lib/gofr-common/secrets/service_creds/gofr-dig.json)
    # Ensure they exist — auto-provision if Vault is available.
    ENSURE_APPROLE="$PROJECT_ROOT/scripts/ensure_approle.sh"
    if [ -x "$ENSURE_APPROLE" ]; then
        "$ENSURE_APPROLE" || {
            warn "AppRole provisioning failed — continuing anyway (auth may not work)"
            warn "Run manually: $ENSURE_APPROLE"
        }
    else
        VAULT_CREDS_FILE="$PROJECT_ROOT/lib/gofr-common/secrets/service_creds/gofr-dig.json"
        if [ -f "$VAULT_CREDS_FILE" ]; then
            ok "Vault AppRole credentials found (baked into image)"
        else
            warn "No AppRole credentials and ensure_approle.sh not executable"
            warn "Run: chmod +x scripts/ensure_approle.sh && scripts/ensure_approle.sh"
        fi
    fi
fi

# ---- Build image if needed --------------------------------------------------
if [ "$FORCE_BUILD" = true ] || ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
    if [ "$FORCE_BUILD" = true ]; then
        info "Force-building production image..."
    else
        info "Image '$IMAGE_NAME' not found — building automatically..."
    fi

    cd "$PROJECT_ROOT"

    # Extract version from pyproject.toml
    VERSION=$(grep -m1 '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
    VERSION="${VERSION:-0.0.0}"

    docker build \
        -f docker/Dockerfile.prod \
        -t "gofr-dig-prod:${VERSION}" \
        -t "$IMAGE_NAME" \
        .

    ok "Built gofr-dig-prod:${VERSION} (also tagged :latest)"
else
    ok "Image '$IMAGE_NAME' already exists (use --build to rebuild)"
fi

# ---- Network ----------------------------------------------------------------
if ! docker network inspect "$NETWORK_NAME" &>/dev/null 2>&1; then
    info "Creating network: $NETWORK_NAME"
    docker network create "$NETWORK_NAME"
else
    ok "Network '$NETWORK_NAME' exists"
fi

# ---- Start compose stack ----------------------------------------------------
echo ""
info "Starting gofr-dig production stack..."

docker compose -f "$COMPOSE_FILE" up -d

# ---- Health check -----------------------------------------------------------
info "Waiting for services to become healthy..."
RETRIES=20
ALL_HEALTHY=false

for i in $(seq 1 $RETRIES); do
    sleep 3

    # Use Docker's own healthcheck status (works from dev container or host)
    MCP_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' gofr-dig-mcp 2>/dev/null || echo "missing")
    MCPO_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' gofr-dig-mcpo 2>/dev/null || echo "missing")
    WEB_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' gofr-dig-web 2>/dev/null || echo "missing")

    if [ "$MCP_HEALTH" = "healthy" ] && [ "$WEB_HEALTH" = "healthy" ] && [ "$MCPO_HEALTH" = "healthy" ]; then
        ALL_HEALTHY=true
        break
    fi

    printf "."
done
echo ""

# Report status per service
for svc in mcp mcpo web; do
    CONTAINER="gofr-dig-${svc}"
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "unknown")
    STATUS=$(docker inspect --format='{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "unknown")
    case "$HEALTH" in
        healthy)  ok "$svc: $STATUS ($HEALTH)" ;;
        starting) warn "$svc: $STATUS ($HEALTH — still starting)" ;;
        *)        warn "$svc: $STATUS ($HEALTH)" ;;
    esac
done

if [ "$ALL_HEALTHY" != true ]; then
    echo ""
    warn "Not all services healthy yet — they may still be starting"
    warn "Check logs: docker compose -f $COMPOSE_FILE logs -f"
fi

# ---- Summary ----------------------------------------------------------------
echo ""
echo "======================================================================="
echo "  gofr-dig production stack is running"
echo "======================================================================="
echo ""
echo "  MCP Server:  http://localhost:${GOFR_DIG_MCP_HOST_PORT}/mcp"
echo "  MCPO Server: http://localhost:${GOFR_DIG_MCPO_HOST_PORT}"
echo "  Web Server:  http://localhost:${GOFR_DIG_WEB_HOST_PORT}"
echo ""
echo "  Network:     ${NETWORK_NAME}"
if [ "$NO_AUTH" = true ]; then
    echo "  Auth:        DISABLED (--no-auth)"
else
    echo "  Auth:        JWT enabled (backend: ${GOFR_DIG_AUTH_BACKEND:-vault})"
fi
echo ""
echo "  Logs:    docker compose -f $COMPOSE_FILE logs -f"
echo "  Status:  docker compose -f $COMPOSE_FILE ps"
echo "  Stop:    $0 --down"
echo "  Rebuild: $0 --build"
echo ""
