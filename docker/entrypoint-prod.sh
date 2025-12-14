#!/bin/bash
# gofr-dig Production Entrypoint
# Starts MCP, MCPO, and Web servers via supervisor
set -e

# Environment variables with defaults
export JWT_SECRET="${JWT_SECRET:-changeme}"
export MCP_PORT="${MCP_PORT:-8030}"
export MCPO_PORT="${MCPO_PORT:-8031}"
export WEB_PORT="${WEB_PORT:-8032}"

# gofr-dig specific environment
export GOFR_DIG_DATA_DIR="${GOFR_DIG_DATA_DIR:-/home/gofr-dig/data}"
export GOFR_DIG_STORAGE_DIR="${GOFR_DIG_STORAGE_DIR:-/home/gofr-dig/data/storage}"
export GOFR_DIG_AUTH_DIR="${GOFR_DIG_AUTH_DIR:-/home/gofr-dig/data/auth}"

# Neo4j connection (optional, for graph operations)
export NEO4J_URI="${NEO4J_URI:-bolt://gofr-neo4j:7687}"
export NEO4J_USER="${NEO4J_USER:-neo4j}"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"

# Path to venv
VENV_PATH="/home/gofr-dig/.venv"

echo "=== gofr-dig Production Container ==="
echo "MCP Port:  ${MCP_PORT}"
echo "MCPO Port: ${MCPO_PORT}"
echo "Web Port:  ${WEB_PORT}"
echo "Data Dir:  ${GOFR_DIG_DATA_DIR}"

# Ensure data directories exist with correct permissions
mkdir -p "${GOFR_DIG_DATA_DIR}" "${GOFR_DIG_STORAGE_DIR}" "${GOFR_DIG_AUTH_DIR}"
chown -R gofr-dig:gofr-dig /home/gofr-dig/data

# Generate supervisor configuration
cat > /etc/supervisor/conf.d/gofr-dig.conf << EOF
[supervisord]
nodaemon=true
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid
user=root

[program:mcp]
command=${VENV_PATH}/bin/python -m app.main_mcp
directory=/home/gofr-dig
user=gofr-dig
autostart=true
autorestart=true
stdout_logfile=/home/gofr-dig/logs/mcp.log
stderr_logfile=/home/gofr-dig/logs/mcp-error.log
environment=PATH="${VENV_PATH}/bin:%(ENV_PATH)s",VIRTUAL_ENV="${VENV_PATH}",JWT_SECRET="%(ENV_JWT_SECRET)s",MCP_PORT="%(ENV_MCP_PORT)s",GOFR_DIG_DATA_DIR="%(ENV_GOFR_DIG_DATA_DIR)s",GOFR_DIG_STORAGE_DIR="%(ENV_GOFR_DIG_STORAGE_DIR)s",GOFR_DIG_AUTH_DIR="%(ENV_GOFR_DIG_AUTH_DIR)s",NEO4J_URI="%(ENV_NEO4J_URI)s",NEO4J_USER="%(ENV_NEO4J_USER)s",NEO4J_PASSWORD="%(ENV_NEO4J_PASSWORD)s"

[program:mcpo]
command=${VENV_PATH}/bin/mcpo --host 0.0.0.0 --port ${MCPO_PORT} -- ${VENV_PATH}/bin/python -m app.main_mcp
directory=/home/gofr-dig
user=gofr-dig
autostart=true
autorestart=true
stdout_logfile=/home/gofr-dig/logs/mcpo.log
stderr_logfile=/home/gofr-dig/logs/mcpo-error.log
environment=PATH="${VENV_PATH}/bin:%(ENV_PATH)s",VIRTUAL_ENV="${VENV_PATH}",JWT_SECRET="%(ENV_JWT_SECRET)s",GOFR_DIG_DATA_DIR="%(ENV_GOFR_DIG_DATA_DIR)s",GOFR_DIG_STORAGE_DIR="%(ENV_GOFR_DIG_STORAGE_DIR)s",GOFR_DIG_AUTH_DIR="%(ENV_GOFR_DIG_AUTH_DIR)s",NEO4J_URI="%(ENV_NEO4J_URI)s",NEO4J_USER="%(ENV_NEO4J_USER)s",NEO4J_PASSWORD="%(ENV_NEO4J_PASSWORD)s"

[program:web]
command=${VENV_PATH}/bin/python -m app.main_web
directory=/home/gofr-dig
user=gofr-dig
autostart=true
autorestart=true
stdout_logfile=/home/gofr-dig/logs/web.log
stderr_logfile=/home/gofr-dig/logs/web-error.log
environment=PATH="${VENV_PATH}/bin:%(ENV_PATH)s",VIRTUAL_ENV="${VENV_PATH}",JWT_SECRET="%(ENV_JWT_SECRET)s",WEB_PORT="%(ENV_WEB_PORT)s",GOFR_DIG_DATA_DIR="%(ENV_GOFR_DIG_DATA_DIR)s",GOFR_DIG_STORAGE_DIR="%(ENV_GOFR_DIG_STORAGE_DIR)s",GOFR_DIG_AUTH_DIR="%(ENV_GOFR_DIG_AUTH_DIR)s",NEO4J_URI="%(ENV_NEO4J_URI)s",NEO4J_USER="%(ENV_NEO4J_USER)s",NEO4J_PASSWORD="%(ENV_NEO4J_PASSWORD)s"
EOF

echo "Starting supervisor..."
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
