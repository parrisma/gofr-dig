#!/bin/bash
# Run GOFR-DIG development container
# Uses gofr-dig-dev:latest image (built from gofr-base:latest)
# Detects host UID/GID so mounted files have correct ownership.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$PROJECT_ROOT/docker"
# gofr-common is now a git submodule at lib/gofr-common, no separate mount needed

# Detect host user's UID/GID (the dev container must match so bind-mounted
# files have the right ownership). Prod/test images always use 1000:1000.
GOFR_UID=$(id -u)
GOFR_GID=$(id -g)

# Container and image names
CONTAINER_NAME="gofr-dig-dev"
IMAGE_NAME="gofr-dig-dev:latest"

# Fixed container-internal paths (must match image layout; do NOT derive from host home).
CONTAINER_HOME="/home/gofr"
CONTAINER_PROJECT_DIR="${CONTAINER_HOME}/devroot/gofr-dig"
CONTAINER_DOC_DIR="${CONTAINER_HOME}/devroot/gofr-doc"

# Primary network for testing; also connects to gofr-net for Vault access
DOCKER_NETWORK="${GOFRDIG_DOCKER_NETWORK:-gofr-test-net}"
GOFR_NETWORK="gofr-net"

usage() {
    cat <<EOF
Usage: $0 [--network NAME]

Options:
  --network NAME     Docker network for the dev container (default: $DOCKER_NETWORK)
  -h, --help         Show this help

Env:
  GOFRDIG_DOCKER_NETWORK  Same as --network
EOF
}

# Parse command line arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --network)
            if [ $# -lt 2 ]; then
                echo "ERROR: --network requires a value" >&2
                usage
                exit 1
            fi
            DOCKER_NETWORK="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

echo "======================================================================="
echo "Starting GOFR-DIG Development Container"
echo "======================================================================="
echo "Host user: $(id -un) (UID=${GOFR_UID}, GID=${GOFR_GID})"
echo "Container will run with --user ${GOFR_UID}:${GOFR_GID}"
echo "Networks: $DOCKER_NETWORK, $GOFR_NETWORK"
echo "Ports: none (dev container is for code editing; prod owns the service ports)"
echo "======================================================================="

# Create docker network if it doesn't exist
if ! docker network inspect "$DOCKER_NETWORK" >/dev/null 2>&1; then
    echo "Creating network: $DOCKER_NETWORK"
    docker network create "$DOCKER_NETWORK"
fi

# Ensure gofr-net exists for Vault/service access
if ! docker network inspect "$GOFR_NETWORK" >/dev/null 2>&1; then
    echo "Creating network: $GOFR_NETWORK"
    docker network create "$GOFR_NETWORK"
fi

# Create docker volume for persistent data
VOLUME_NAME="gofr-dig-data-dev"
if ! docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
    echo "Creating volume: $VOLUME_NAME"
    docker volume create "$VOLUME_NAME"
fi

# Create shared secrets volume (shared across all GOFR projects)
SECRETS_VOLUME="gofr-secrets"
if ! docker volume inspect "$SECRETS_VOLUME" >/dev/null 2>&1; then
    echo "Creating volume: $SECRETS_VOLUME"
    docker volume create "$SECRETS_VOLUME"
fi

# Stop and remove existing container
if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
    echo "Stopping existing container: $CONTAINER_NAME"
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
fi

# Detect Docker socket GID for group mapping
DOCKER_SOCKET="/var/run/docker.sock"
DOCKER_GID_ARGS=""
if [ -S "$DOCKER_SOCKET" ]; then
    DOCKER_GID=$(stat -c '%g' "$DOCKER_SOCKET")
    echo "Docker socket GID: $DOCKER_GID"
    DOCKER_GID_ARGS="-v $DOCKER_SOCKET:$DOCKER_SOCKET:rw --group-add $DOCKER_GID"
else
    echo "Warning: Docker socket not found at $DOCKER_SOCKET - docker commands will not work inside container"
fi

# ---- Pre-flight checks ------------------------------------------------------

# Verify image exists
if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo ""
    echo "ERROR: Image '$IMAGE_NAME' not found."
    echo "  Build it first:  ./docker/build-dev.sh"
    echo ""
    exit 1
fi

# Ensure gofr-common submodule is initialised
COMMON_DIR="$PROJECT_ROOT/lib/gofr-common"
if [ ! -f "$COMMON_DIR/pyproject.toml" ]; then
    echo "gofr-common submodule not initialised — initialising now..."
    cd "$PROJECT_ROOT"
    git submodule update --init --recursive
    if [ ! -f "$COMMON_DIR/pyproject.toml" ]; then
        echo ""
        echo "ERROR: Failed to initialise gofr-common submodule."
        echo "  $COMMON_DIR still has no pyproject.toml."
        echo "  Try manually: cd $PROJECT_ROOT && git submodule update --init --recursive"
        echo ""
        exit 1
    fi
    echo "gofr-common submodule initialised OK."
fi

# ---- Run container ----------------------------------------------------------
# NOTE: No host port bindings — the dev container is for code editing.
# Production containers (via start-prod.sh) own the service ports.
# Always run as the host user's UID/GID so bind-mounted files have correct ownership.
USER_ARGS="--user ${GOFR_UID}:${GOFR_GID}"

echo "Running: docker run -d --name $CONTAINER_NAME ..."
CONTAINER_ID=$(docker run -d \
    --name "$CONTAINER_NAME" \
    --network "$DOCKER_NETWORK" \
    -w "${CONTAINER_PROJECT_DIR}" \
    $USER_ARGS \
    -v "$PROJECT_ROOT:${CONTAINER_PROJECT_DIR}:rw" \
    -v "${VOLUME_NAME}:${CONTAINER_PROJECT_DIR}/data:rw" \
    -v "${SECRETS_VOLUME}:${CONTAINER_PROJECT_DIR}/secrets:rw" \
    -v "$PROJECT_ROOT/../gofr-doc:${CONTAINER_DOC_DIR}:ro" \
    $DOCKER_GID_ARGS \
    -e GOFR_DIG_PROJECT_DIR="${CONTAINER_PROJECT_DIR}" \
    -e GOFRDIG_ENV=development \
    -e GOFRDIG_DEBUG=true \
    -e GOFRDIG_LOG_LEVEL=DEBUG \
    "$IMAGE_NAME" 2>&1) || {
    echo ""
    echo "ERROR: docker run failed."
    echo "  Output: $CONTAINER_ID"
    echo ""
    exit 1
}

# ---- Verify container is actually running -----------------------------------
echo "Waiting for container to stabilise..."
sleep 2

# Connect to gofr-net for Vault and other GOFR services
if ! docker network inspect "$GOFR_NETWORK" --format '{{range .Containers}}{{.Name}} {{end}}' | grep -Fq "$CONTAINER_NAME"; then
    echo "Connecting to $GOFR_NETWORK..."
    docker network connect "$GOFR_NETWORK" "$CONTAINER_NAME"
fi

CONTAINER_STATE=$(docker inspect --format '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "not_found")
CONTAINER_RUNNING=$(docker inspect --format '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || echo "false")

if [[ "$CONTAINER_STATE" != "running" || "$CONTAINER_RUNNING" != "true" ]]; then
    EXIT_CODE=$(docker inspect --format '{{.State.ExitCode}}' "$CONTAINER_NAME" 2>/dev/null || echo "?")
    echo ""
    echo "======================================================================="
    echo "ERROR: Container '$CONTAINER_NAME' is NOT running"
    echo "======================================================================="
    echo "  State:     $CONTAINER_STATE"
    echo "  Exit code: $EXIT_CODE"
    echo ""
    echo "  Last 20 lines of container logs:"
    echo "  ---------------------------------"
    docker logs --tail 20 "$CONTAINER_NAME" 2>&1 | sed 's/^/  /'
    echo ""
    echo "  Full logs:  docker logs $CONTAINER_NAME"
    echo "  Inspect:    docker inspect $CONTAINER_NAME"
    echo ""
    exit 1
fi

# ---- Success ----------------------------------------------------------------
echo ""
echo "======================================================================="
echo "Container RUNNING: $CONTAINER_NAME"
echo "======================================================================="
echo "  ID:      ${CONTAINER_ID:0:12}"
echo "  State:   $CONTAINER_STATE"
echo "  Image:   $IMAGE_NAME"
echo "  Networks: $DOCKER_NETWORK, $GOFR_NETWORK"
echo "  Docker:  $( [ -n "$DOCKER_GID_ARGS" ] && echo 'socket mounted (DinD ready)' || echo 'socket NOT mounted' )"
echo ""
echo "Useful commands:"
echo "  docker logs -f $CONTAINER_NAME          # Follow logs"
echo "  docker exec -it $CONTAINER_NAME bash    # Shell access"
echo "  docker stop $CONTAINER_NAME             # Stop container"
