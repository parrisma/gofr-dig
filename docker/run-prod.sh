#!/bin/bash
# Run gofr-dig production container with proper volumes and networking
set -e

CONTAINER_NAME="gofr-dig-prod"
IMAGE_NAME="gofr-dig-prod:latest"
NETWORK_NAME="gofr-net"

# Port assignments for gofr-dig
MCP_PORT="${GOFR_DIG_MCP_PORT:-8030}"
MCPO_PORT="${GOFR_DIG_MCPO_PORT:-8031}"
WEB_PORT="${GOFR_DIG_WEB_PORT:-8032}"

# JWT Secret (required)
JWT_SECRET="${GOFR_DIG_JWT_SECRET:-}"

if [ -z "$JWT_SECRET" ]; then
    echo "ERROR: GOFR_DIG_JWT_SECRET environment variable is required"
    echo "Usage: GOFR_DIG_JWT_SECRET=your-secret ./run-prod.sh"
    exit 1
fi

# Neo4j connection (optional)
NEO4J_URI="${NEO4J_URI:-bolt://gofr-neo4j:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"

echo "=== gofr-dig Production Container ==="

# Create network if it doesn't exist
if ! docker network inspect ${NETWORK_NAME} >/dev/null 2>&1; then
    echo "Creating network: ${NETWORK_NAME}"
    docker network create ${NETWORK_NAME}
fi

# Create volumes if they don't exist
for vol in gofr-dig-data gofr-dig-logs; do
    if ! docker volume inspect ${vol} >/dev/null 2>&1; then
        echo "Creating volume: ${vol}"
        docker volume create ${vol}
    fi
done

# Stop existing container if running
if docker ps -q -f name=${CONTAINER_NAME} | grep -q .; then
    echo "Stopping existing container..."
    docker stop ${CONTAINER_NAME}
fi

# Remove existing container if exists
if docker ps -aq -f name=${CONTAINER_NAME} | grep -q .; then
    echo "Removing existing container..."
    docker rm ${CONTAINER_NAME}
fi

echo "Starting ${CONTAINER_NAME}..."
echo "  MCP Port:  ${MCP_PORT}"
echo "  MCPO Port: ${MCPO_PORT}"
echo "  Web Port:  ${WEB_PORT}"

docker run -d \
    --name ${CONTAINER_NAME} \
    --network ${NETWORK_NAME} \
    -v gofr-dig-data:/home/gofr-dig/data \
    -v gofr-dig-logs:/home/gofr-dig/logs \
    -p ${MCP_PORT}:8030 \
    -p ${MCPO_PORT}:8031 \
    -p ${WEB_PORT}:8032 \
    -e JWT_SECRET="${JWT_SECRET}" \
    -e MCP_PORT=8030 \
    -e MCPO_PORT=8031 \
    -e WEB_PORT=8032 \
    -e NEO4J_URI="${NEO4J_URI}" \
    -e NEO4J_USER="${NEO4J_USER}" \
    -e NEO4J_PASSWORD="${NEO4J_PASSWORD}" \
    ${IMAGE_NAME}

# Wait for container to start
sleep 2

if docker ps -q -f name=${CONTAINER_NAME} | grep -q .; then
    echo ""
    echo "=== Container Started Successfully ==="
    echo "MCP Server:  http://localhost:${MCP_PORT}/mcp"
    echo "MCPO Server: http://localhost:${MCPO_PORT}"
    echo "Web Server:  http://localhost:${WEB_PORT}"
    echo ""
    echo "Volumes:"
    echo "  Data: gofr-dig-data"
    echo "  Logs: gofr-dig-logs"
    echo ""
    echo "Commands:"
    echo "  Logs:   docker logs -f ${CONTAINER_NAME}"
    echo "  Stop:   ./stop-prod.sh"
    echo "  Shell:  docker exec -it ${CONTAINER_NAME} bash"
else
    echo "ERROR: Container failed to start"
    docker logs ${CONTAINER_NAME}
    exit 1
fi
