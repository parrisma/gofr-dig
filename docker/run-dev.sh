#!/bin/bash
# =============================================================================
# GOFR-DIG Docker Development Container Launcher
# =============================================================================
# Usage: ./run-dev.sh [options]
#
# Options:
#   --network NAME      Docker network name (default: from gofr-dig.env or gofr-net)
#   --container NAME    Container name (default: from gofr-dig.env or gofr-dig_dev)
#   --volume NAME       Data volume name (default: from gofr-dig.env or gofr-dig_data_dev)
#   --host HOST         Bind host for all services (default: 0.0.0.0)
#   --mcp-port PORT     MCP server port (default: from gofr-dig.env or 8030)
#   --mcpo-port PORT    MCPO wrapper port (default: from gofr-dig.env or 8031)
#   --web-port PORT     Web server port (default: from gofr-dig.env or 8032)
#
# Environment Variables (from gofr-dig.env):
#   GOFR_DIG_NETWORK, GOFR_DIG_CONTAINER, GOFR_DIG_DATA_VOLUME
#   GOFR_DIG_MCP_PORT, GOFR_DIG_MCPO_PORT, GOFR_DIG_WEB_PORT
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source centralized configuration if available
if [ -f "$PROJECT_ROOT/scripts/gofr-dig.env" ]; then
    source "$PROJECT_ROOT/scripts/gofr-dig.env"
fi

# Set defaults (using gofr-dig.env values if available)
NETWORK="${GOFR_DIG_NETWORK:-gofr-net}"
CONTAINER="${GOFR_DIG_CONTAINER:-gofr-dig_dev}"
VOLUME="${GOFR_DIG_DATA_VOLUME:-gofr-dig_data_dev}"
HOST="${GOFR_DIG_HOST:-0.0.0.0}"
MCP_PORT="${GOFR_DIG_MCP_PORT:-8030}"
MCPO_PORT="${GOFR_DIG_MCPO_PORT:-8031}"
WEB_PORT="${GOFR_DIG_WEB_PORT:-8032}"

# Parse command line arguments (override env vars)
while [[ $# -gt 0 ]]; do
    case $1 in
        --network)
            NETWORK="$2"
            shift 2
            ;;
        --container)
            CONTAINER="$2"
            shift 2
            ;;
        --volume)
            VOLUME="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --mcp-port)
            MCP_PORT="$2"
            shift 2
            ;;
        --mcpo-port)
            MCPO_PORT="$2"
            shift 2
            ;;
        --web-port)
            WEB_PORT="$2"
            shift 2
            ;;
        *)
            # Legacy positional args support: WEB_PORT MCP_PORT MCPO_PORT
            if [[ "$1" =~ ^[0-9]+$ ]]; then
                WEB_PORT="$1"
                shift
                if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
                    MCP_PORT="$1"
                    shift
                    if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
                        MCPO_PORT="$1"
                        shift
                    fi
                fi
            else
                echo "Unknown option: $1"
                exit 1
            fi
            ;;
    esac
done

# Create docker network if it doesn't exist
echo "Checking for $NETWORK network..."
if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
    echo "Creating $NETWORK network..."
    docker network create "$NETWORK"
else
    echo "Network $NETWORK already exists"
fi

# Create docker volume for persistent data if it doesn't exist
echo "Checking for $VOLUME volume..."
if ! docker volume inspect "$VOLUME" >/dev/null 2>&1; then
    echo "Creating $VOLUME volume..."
    docker volume create "$VOLUME"
    VOLUME_CREATED=true
else
    echo "Volume $VOLUME already exists"
    VOLUME_CREATED=false
fi

# Stop and remove existing container if it exists
echo "Stopping existing $CONTAINER container..."
docker stop "$CONTAINER" 2>/dev/null || true

echo "Removing existing $CONTAINER container..."
docker rm "$CONTAINER" 2>/dev/null || true

echo "Starting new $CONTAINER container..."
echo "Mounting $HOME/devroot/gofr-dig to /home/gofr/devroot/gofr-dig in container"
echo "Mounting $HOME/.ssh to /home/gofr/.ssh (read-only) in container"
echo "Mounting $VOLUME volume to /home/gofr/devroot/gofr-dig/data in container"
echo "Network: $NETWORK"
echo "Web port: $WEB_PORT, MCP port: $MCP_PORT, MCPO port: $MCPO_PORT"

docker run -d \
--name "$CONTAINER" \
--network "$NETWORK" \
--user $(id -u):$(id -g) \
-v "$HOME/devroot/gofr-dig":/home/gofr/devroot/gofr-dig \
-v "$HOME/.ssh:/home/gofr/.ssh:ro" \
-v "$VOLUME":/home/gofr/devroot/gofr-dig/data \
-e GOFR_DIG_HOST="$HOST" \
-e GOFR_DIG_MCP_PORT="$MCP_PORT" \
-e GOFR_DIG_MCPO_PORT="$MCPO_PORT" \
-e GOFR_DIG_WEB_PORT="$WEB_PORT" \
-e GOFR_DIG_NETWORK="$NETWORK" \
-p $MCP_PORT:$MCP_PORT \
-p $MCPO_PORT:$MCPO_PORT \
-p $WEB_PORT:$WEB_PORT \
gofr-dig_dev:latest

if docker ps -q -f name="$CONTAINER" | grep -q .; then
    echo "Container $CONTAINER is now running"
    
    # Fix volume permissions if it was just created
    if [ "$VOLUME_CREATED" = true ]; then
        echo "Fixing permissions on newly created volume..."
        docker exec -u root "$CONTAINER" chown -R gofr:gofr /home/gofr/devroot/gofr-dig/data
        echo "Volume permissions fixed"
    fi
    
    echo ""
    echo "==================================================================="
    echo "OpenWebUI Integration:"
    echo "  MCPO Proxy:    http://localhost:$MCPO_PORT"
    echo "                 (Use this URL in OpenWebUI -> Connections -> Tools)"
    echo ""
    echo "Development Container Access:"
    echo "  Shell:         docker exec -it $CONTAINER /bin/bash"
    echo "  VS Code:       Attach to container '$CONTAINER'"
    echo ""
    echo "Internal Services (for debugging):"
    echo "  Web Server:    http://localhost:$WEB_PORT"
    echo "  MCP Server:    http://localhost:$MCP_PORT/mcp"
    echo ""
    echo "Access from $NETWORK (other containers):"
    echo "  MCPO Proxy:    http://$CONTAINER:$MCPO_PORT"
    echo ""
    echo "Data & Storage:"
    echo "  Volume:        $VOLUME"
    echo "  Source Mount:  $HOME/devroot/gofr-dig (live-reload)"
    echo "==================================================================="
    echo ""
else
    echo "ERROR: Container $CONTAINER failed to start"
    exit 1
fi