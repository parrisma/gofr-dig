#!/bin/bash
# =============================================================================
# gofr-dig Production Entrypoint
# Starts MCP, MCPO, and Web servers via supervisor
# =============================================================================
#
# Environment variables (all prefixed with GOFR_DIG_ to match Python code):
#   GOFR_DIG_JWT_SECRET   - JWT signing secret
#   GOFR_DIG_MCP_PORT     - MCP server port (default: 8070)
#   GOFR_DIG_MCPO_PORT    - MCPO proxy port (default: 8071)
#   GOFR_DIG_WEB_PORT     - Web server port (default: 8072)
#   GOFR_DIG_DATA_DIR     - Data root directory
#   GOFR_DIG_STORAGE_DIR  - Storage directory
#   GOFR_DIG_NO_AUTH      - Set to "1" to disable authentication
# =============================================================================
set -e

# --- Environment with defaults (all GOFR_DIG_ prefixed) ---------------------
# These names MUST match what the Python code reads via
# resolve_auth_config(env_prefix="GOFR_DIG") and os.environ.get("GOFR_DIG_*")
export GOFR_DIG_JWT_SECRET="${GOFR_DIG_JWT_SECRET:-}"
export GOFR_DIG_MCP_PORT="${GOFR_DIG_MCP_PORT:-8070}"
export GOFR_DIG_MCPO_PORT="${GOFR_DIG_MCPO_PORT:-8071}"
export GOFR_DIG_WEB_PORT="${GOFR_DIG_WEB_PORT:-8072}"
export GOFR_DIG_DATA_DIR="${GOFR_DIG_DATA_DIR:-/home/gofr-dig/data}"
export GOFR_DIG_STORAGE_DIR="${GOFR_DIG_STORAGE_DIR:-/home/gofr-dig/data/storage}"
export GOFR_DIG_NO_AUTH="${GOFR_DIG_NO_AUTH:-}"

# Neo4j connection (optional)
export NEO4J_URI="${NEO4J_URI:-bolt://gofr-neo4j:7687}"
export NEO4J_USER="${NEO4J_USER:-neo4j}"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"

# Path to venv
VENV_PATH="/home/gofr-dig/.venv"

# --- Auth flag ---------------------------------------------------------------
# If GOFR_DIG_NO_AUTH=1, pass --no-auth to the Python servers
AUTH_FLAG=""
if [ "${GOFR_DIG_NO_AUTH}" = "1" ]; then
    AUTH_FLAG="--no-auth"
    echo "WARNING: Authentication is DISABLED (GOFR_DIG_NO_AUTH=1)"
fi

echo "=== gofr-dig Production Container ==="
echo "MCP Port:  ${GOFR_DIG_MCP_PORT}"
echo "MCPO Port: ${GOFR_DIG_MCPO_PORT}"
echo "Web Port:  ${GOFR_DIG_WEB_PORT}"
echo "Data Dir:  ${GOFR_DIG_DATA_DIR}"
echo "Auth:      $([ -n "${AUTH_FLAG}" ] && echo 'DISABLED' || echo 'JWT enabled')"

# --- Ensure data directories exist -------------------------------------------
mkdir -p "${GOFR_DIG_DATA_DIR}" "${GOFR_DIG_STORAGE_DIR}"
chown -R gofr-dig:gofr-dig /home/gofr-dig/data

# --- Shared supervisor environment ------------------------------------------
# All GOFR_DIG_* env vars are passed through to each program.
# supervisor uses %(ENV_VARNAME)s to reference the container environment.
SHARED_ENV="PATH=\"${VENV_PATH}/bin:%(ENV_PATH)s\",VIRTUAL_ENV=\"${VENV_PATH}\""
SHARED_ENV="${SHARED_ENV},GOFR_DIG_JWT_SECRET=\"%(ENV_GOFR_DIG_JWT_SECRET)s\""
SHARED_ENV="${SHARED_ENV},GOFR_DIG_MCP_PORT=\"%(ENV_GOFR_DIG_MCP_PORT)s\""
SHARED_ENV="${SHARED_ENV},GOFR_DIG_MCPO_PORT=\"%(ENV_GOFR_DIG_MCPO_PORT)s\""
SHARED_ENV="${SHARED_ENV},GOFR_DIG_WEB_PORT=\"%(ENV_GOFR_DIG_WEB_PORT)s\""
SHARED_ENV="${SHARED_ENV},GOFR_DIG_DATA_DIR=\"%(ENV_GOFR_DIG_DATA_DIR)s\""
SHARED_ENV="${SHARED_ENV},GOFR_DIG_STORAGE_DIR=\"%(ENV_GOFR_DIG_STORAGE_DIR)s\""
SHARED_ENV="${SHARED_ENV},NEO4J_URI=\"%(ENV_NEO4J_URI)s\""
SHARED_ENV="${SHARED_ENV},NEO4J_USER=\"%(ENV_NEO4J_USER)s\""
SHARED_ENV="${SHARED_ENV},NEO4J_PASSWORD=\"%(ENV_NEO4J_PASSWORD)s\""

# --- Generate supervisor configuration --------------------------------------
cat > /etc/supervisor/conf.d/gofr-dig.conf << EOF
[supervisord]
nodaemon=true
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid
user=root

[program:mcp]
command=${VENV_PATH}/bin/python -m app.main_mcp ${AUTH_FLAG}
directory=/home/gofr-dig
user=gofr-dig
autostart=true
autorestart=true
stdout_logfile=/home/gofr-dig/logs/mcp.log
stderr_logfile=/home/gofr-dig/logs/mcp-error.log
environment=${SHARED_ENV}

[program:mcpo]
command=${VENV_PATH}/bin/mcpo --host 0.0.0.0 --port ${GOFR_DIG_MCPO_PORT} -- ${VENV_PATH}/bin/python -m app.main_mcp ${AUTH_FLAG}
directory=/home/gofr-dig
user=gofr-dig
autostart=true
autorestart=true
stdout_logfile=/home/gofr-dig/logs/mcpo.log
stderr_logfile=/home/gofr-dig/logs/mcpo-error.log
environment=${SHARED_ENV}

[program:web]
command=${VENV_PATH}/bin/python -m app.main_web ${AUTH_FLAG}
directory=/home/gofr-dig
user=gofr-dig
autostart=true
autorestart=true
stdout_logfile=/home/gofr-dig/logs/web.log
stderr_logfile=/home/gofr-dig/logs/web-error.log
environment=${SHARED_ENV}
EOF

echo "Starting supervisor..."
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
