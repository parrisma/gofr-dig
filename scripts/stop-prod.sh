#!/bin/bash
# Stop gofr-dig production stack gracefully
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$PROJECT_ROOT/docker"
COMPOSE_FILE="$DOCKER_DIR/compose.prod.yml"
PORTS_ENV="$PROJECT_ROOT/lib/gofr-common/config/gofr_ports.env"

# Source ports so compose can resolve variables
if [ -f "$PORTS_ENV" ]; then
    set -a && source "$PORTS_ENV" && set +a
fi

echo "Stopping gofr-dig production stack..."

docker compose -f "$COMPOSE_FILE" down "$@"

echo "Stack stopped"
