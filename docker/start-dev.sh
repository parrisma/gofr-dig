#!/bin/bash
# =============================================================================
# GOFR-DIG Development Start Script
# =============================================================================
# One-command dev stack using docker compose.
#
# What this does:
#   1. Checks prerequisites (docker, docker compose)
#   2. Builds the dev image if it doesn't exist (or with --build)
#   3. Sources centralized port config from gofr_ports.env
#   4. Creates the docker network if missing
#   5. Starts the compose dev stack (mcp, mcpo, web as separate services)
#   6. Runs health checks to verify services are up
#
# Usage:
#   ./start-dev.sh                     # Start (auto-builds if image missing)
#   ./start-dev.sh --build             # Force rebuild before starting
#   ./start-dev.sh --port-offset 100   # Shift host ports by N (e.g., 8070→8170)
#   ./start-dev.sh --down              # Stop and remove all dev services
#
# Notes:
#   - This script only manages the dev compose stack (mcp/mcpo/web)
#   - It does NOT stop the gofr-dig-dev devcontainer
#   - Dev stack runs with --no-auth (see compose.dev.yml)
#
# Ports are read from lib/gofr-common/config/gofr_ports.env (single source of truth)
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---- Configuration ----------------------------------------------------------
IMAGE_NAME="gofr-dig-prod:latest"
COMPOSE_FILE="$SCRIPT_DIR/compose.dev.yml"
NETWORK_NAME="gofr-test-net"
PORTS_ENV="$PROJECT_ROOT/lib/gofr-common/config/gofr_ports.env"

FORCE_BUILD=false
DO_DOWN=false
PORT_OFFSET=0

# ---- Parse arguments --------------------------------------------------------
while [ $# -gt 0 ]; do
    case "$1" in
        --build)     FORCE_BUILD=true; shift ;;
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
            echo "Usage: $0 [--build] [--port-offset N] [--down] [--help]"
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
    # No offset — dev/test stack always uses test ports (prod + 100)
    export GOFR_DIG_MCP_HOST_PORT=${GOFR_DIG_MCP_PORT_TEST}
    export GOFR_DIG_MCPO_HOST_PORT=${GOFR_DIG_MCPO_PORT_TEST}
    export GOFR_DIG_WEB_HOST_PORT=${GOFR_DIG_WEB_PORT_TEST}
    ok "Ports loaded — test ports (MCP=${GOFR_DIG_MCP_HOST_PORT}, MCPO=${GOFR_DIG_MCPO_HOST_PORT}, Web=${GOFR_DIG_WEB_HOST_PORT})"
fi

# ---- Handle --down ----------------------------------------------------------
if [ "$DO_DOWN" = true ]; then
    info "Stopping gofr-dig dev stack..."
    docker compose -f "$COMPOSE_FILE" down
    ok "Dev stack stopped"
    exit 0
fi

# ---- Build image if needed --------------------------------------------------
if [ "$FORCE_BUILD" = true ] || ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
    if [ "$FORCE_BUILD" = true ]; then
        info "Force-building dev image..."
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
info "Starting gofr-dig dev stack..."

docker compose -f "$COMPOSE_FILE" up -d

# ---- Health check -----------------------------------------------------------
info "Waiting for services to become healthy..."
RETRIES=20
ALL_HEALTHY=false

for i in $(seq 1 $RETRIES); do
    sleep 3

    # Use Docker's own healthcheck status (works from dev container or host)
    MCP_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' gofr-dig-mcp-test 2>/dev/null || echo "missing")
    MCPO_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' gofr-dig-mcpo-test 2>/dev/null || echo "missing")
    WEB_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' gofr-dig-web-test 2>/dev/null || echo "missing")

    if [ "$MCP_HEALTH" = "healthy" ] && [ "$WEB_HEALTH" = "healthy" ] && [ "$MCPO_HEALTH" = "healthy" ]; then
        ALL_HEALTHY=true
        break
    fi

    printf "."
done
echo ""

# Report status per service
for svc in mcp mcpo web; do
    CONTAINER="gofr-dig-${svc}-test"
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "unknown")
    STATUS=$(docker inspect --format='{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "unknown")
    case "$HEALTH" in
        *healthy*) ok "$svc: $STATUS" ;;
        *running*) warn "$svc: $STATUS (not yet healthy)" ;;
        *)         warn "$svc: $STATUS" ;;
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
echo "  gofr-dig dev stack is running"
echo "======================================================================="
echo ""
echo "  MCP Server:  http://localhost:${GOFR_DIG_MCP_HOST_PORT}/mcp"
echo "  MCPO Server: http://localhost:${GOFR_DIG_MCPO_HOST_PORT}"
echo "  Web Server:  http://localhost:${GOFR_DIG_WEB_HOST_PORT}"
echo ""
echo "  Network:     ${NETWORK_NAME}"
echo "  Auth:        DISABLED (dev stack uses --no-auth)"
echo ""
echo "  Logs:    docker compose -f $COMPOSE_FILE logs -f"
echo "  Status:  docker compose -f $COMPOSE_FILE ps"
echo "  Stop:    $0 --down"
echo "  Rebuild: $0 --build"
echo ""