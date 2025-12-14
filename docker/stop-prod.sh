#!/bin/bash
# Stop gofr-dig production container gracefully
set -e

CONTAINER_NAME="gofr-dig-prod"

echo "Stopping ${CONTAINER_NAME}..."

if docker ps -q -f name=${CONTAINER_NAME} | grep -q .; then
    docker stop -t 30 ${CONTAINER_NAME}
    echo "Container stopped"
else
    echo "Container is not running"
fi

# Optionally remove the container
if [ "$1" = "--rm" ]; then
    if docker ps -aq -f name=${CONTAINER_NAME} | grep -q .; then
        docker rm ${CONTAINER_NAME}
        echo "Container removed"
    fi
fi
