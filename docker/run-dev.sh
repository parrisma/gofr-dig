#!/bin/bash
# Run GOFR-DIG development container
# Uses gofr-dig-dev:latest image (built from gofr-base:latest)
# Standard user: gofr (UID 1000, GID 1000)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# gofr-common is now a git submodule at lib/gofr-common, no separate mount needed

# Standard GOFR user - all projects use same user
GOFR_USER="gofr"
GOFR_UID=1000
GOFR_GID=1000

# Container and image names
CONTAINER_NAME="gofr-dig-dev"
IMAGE_NAME="gofr-dig-dev:latest"

# Primary network for testing; also connects to gofr-net for Vault access
DOCKER_NETWORK="${GOFRDIG_DOCKER_NETWORK:-gofr-test-net}"
GOFR_NETWORK="gofr-net"

# Parse command line arguments
while [ $# -gt 0 ]; do
    case $1 in
        --network)
            DOCKER_NETWORK="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--network NAME]"
            exit 1
            ;;
    esac
done

echo "======================================================================="
echo "Starting GOFR-DIG Development Container"
echo "======================================================================="
echo "User: ${GOFR_USER} (UID=${GOFR_UID}, GID=${GOFR_GID})"
echo "Networks: $DOCKER_NETWORK, $GOFR_NETWORK"
echo "Ports: none (dev container is for code editing; prod owns 8070-8072)"
echo "======================================================================="

# Create docker network if it doesn't exist
if ! docker network inspect $DOCKER_NETWORK >/dev/null 2>&1; then
    echo "Creating network: $DOCKER_NETWORK"
    docker network create $DOCKER_NETWORK
fi

# Ensure gofr-net exists for Vault/service access
if ! docker network inspect $GOFR_NETWORK >/dev/null 2>&1; then
    echo "Creating network: $GOFR_NETWORK"
    docker network create $GOFR_NETWORK
fi

# Create docker volume for persistent data
VOLUME_NAME="gofr-dig-data-dev"
if ! docker volume inspect $VOLUME_NAME >/dev/null 2>&1; then
    echo "Creating volume: $VOLUME_NAME"
    docker volume create $VOLUME_NAME
fi

# Stop and remove existing container
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
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
# Production containers (via start-prod.sh) own ports 8070-8072.
echo "Running: docker run -d --name $CONTAINER_NAME ..."
CONTAINER_ID=$(docker run -d \
    --name "$CONTAINER_NAME" \
    --network "$DOCKER_NETWORK" \
    -v "$PROJECT_ROOT:/home/gofr/devroot/gofr-dig:rw" \
    -v ${VOLUME_NAME}:/home/gofr/devroot/gofr-dig/data:rw \
    $DOCKER_GID_ARGS \
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
if ! docker network inspect $GOFR_NETWORK --format '{{range .Containers}}{{.Name}} {{end}}' | grep -q "$CONTAINER_NAME"; then
    echo "Connecting to $GOFR_NETWORK..."
    docker network connect $GOFR_NETWORK "$CONTAINER_NAME"
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
