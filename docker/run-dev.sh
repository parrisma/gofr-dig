#!/bin/sh

# Usage: ./run-dev.sh [WEB_PORT] [MCP_PORT] [MCPO_PORT]
# Defaults: WEB_PORT=8032, MCP_PORT=8030, MCPO_PORT=8031
# Example: ./run-dev.sh 9032 9030 9031

# Parse command line arguments
WEB_PORT=${1:-8032}
MCP_PORT=${2:-8030}
MCPO_PORT=${3:-8031}

# Create docker network if it doesn't exist
echo "Checking for gofr-net network..."
if ! docker network inspect gofr-net >/dev/null 2>&1; then
    echo "Creating gofr-net network..."
    docker network create gofr-net
else
    echo "Network gofr-net already exists"
fi

# Create docker volume for persistent data if it doesn't exist
echo "Checking for gofr-dig_data_dev volume..."
if ! docker volume inspect gofr-dig_data_dev >/dev/null 2>&1; then
    echo "Creating gofr-dig_data_dev volume..."
    docker volume create gofr-dig_data_dev
    VOLUME_CREATED=true
else
    echo "Volume gofr-dig_data_dev already exists"
    VOLUME_CREATED=false
fi

# Stop and remove existing container if it exists
echo "Stopping existing gofr-dig_dev container..."
docker stop gofr-dig_dev 2>/dev/null || true

echo "Removing existing gofr-dig_dev container..."
docker rm gofr-dig_dev 2>/dev/null || true

echo "Starting new gofr-dig_dev container..."
echo "Mounting $HOME/devroot/gofr-dig to /home/gofr/devroot/gofr-dig in container"
echo "Mounting $HOME/.ssh to /home/gofr/.ssh (read-only) in container"
echo "Mounting gofr-dig_data_dev volume to /home/gofr/devroot/gofr-dig/data in container"
echo "Web port: $WEB_PORT, MCP port: $MCP_PORT, MCPO port: $MCPO_PORT"

docker run -d \
--name gofr-dig_dev \
--network gofr-net \
--user $(id -u):$(id -g) \
-v "$HOME/devroot/gofr-dig":/home/gofr/devroot/gofr-dig \
-v "$HOME/.ssh:/home/gofr/.ssh:ro" \
-v gofr-dig_data_dev:/home/gofr/devroot/gofr-dig/data \
-p $MCP_PORT:8030 \
-p $MCPO_PORT:8031 \
-p $WEB_PORT:8032 \
gofr-dig_dev:latest

if docker ps -q -f name=gofr-dig_dev | grep -q .; then
    echo "Container gofr-dig_dev is now running"
    
    # Fix volume permissions if it was just created
    if [ "$VOLUME_CREATED" = true ]; then
        echo "Fixing permissions on newly created volume..."
        docker exec -u root gofr-dig_dev chown -R gofr:gofr /home/gofr/devroot/gofr-dig/data
        echo "Volume permissions fixed"
    fi
    
    echo ""
    echo "==================================================================="
    echo "Development Container Access:"
    echo "  Shell:         docker exec -it gofr-dig_dev /bin/bash"
    echo "  VS Code:       Attach to container 'gofr-dig_dev'"
    echo ""
    echo "Access from Host Machine:"
    echo "  Web Server:    http://localhost:$WEB_PORT"
    echo "  MCP Server:    http://localhost:$MCP_PORT/mcp"
    echo "  MCPO Proxy:    http://localhost:$MCPO_PORT"
    echo ""
    echo "Access from gofr-net (other containers):"
    echo "  Web Server:    http://gofr-dig_dev:8032"
    echo "  MCP Server:    http://gofr-dig_dev:8030/mcp"
    echo "  MCPO Proxy:    http://gofr-dig_dev:8031"
    echo ""
    echo "Data & Storage:"
    echo "  Volume:        gofr-dig_data_dev"
    echo "  Source Mount:  $HOME/devroot/gofr-dig (live-reload)"
    echo "==================================================================="
    echo ""
else
    echo "ERROR: Container gofr-dig_dev failed to start"
    exit 1
fi