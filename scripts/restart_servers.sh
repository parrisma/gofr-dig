#!/bin/bash
# GOFR-DIG Server Restart Script
# Wrapper for the shared restart_servers.sh script
#
# Usage: ./restart_servers.sh [OPTIONS]
#
# Options:
#   --env PROD|TEST     Set environment (default: PROD)
#   --host HOST         Set bind host for all servers (default: 0.0.0.0)
#   --mcp-port PORT     Override MCP server port
#   --mcp-host HOST     Override MCP server host
#   --mcpo-port PORT    Override MCPO wrapper port
#   --mcpo-host HOST    Override MCPO wrapper host
#   --web-port PORT     Override Web server port
#   --web-host HOST     Override Web server host
#   --kill-all          Stop all servers and exit

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_SCRIPTS="$SCRIPT_DIR/../../gofr-common/scripts"

# Check for lib/gofr-common location first (inside container)
if [ -d "$SCRIPT_DIR/../lib/gofr-common/scripts" ]; then
    COMMON_SCRIPTS="$SCRIPT_DIR/../lib/gofr-common/scripts"
fi

# Source centralized configuration (defaults to PROD for restart script)
export GOFR_DIG_ENV="${GOFR_DIG_ENV:-PROD}"
source "$SCRIPT_DIR/gofr-dig.env"

# Parse command line arguments (these override env vars)
PASSTHROUGH_ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            export GOFR_DIG_ENV="$2"
            shift 2
            ;;
        --host)
            export GOFR_DIG_HOST="$2"
            shift 2
            ;;
        --mcp-port)
            export GOFR_DIG_MCP_PORT="$2"
            shift 2
            ;;
        --mcp-host)
            export GOFR_DIG_MCP_HOST="$2"
            shift 2
            ;;
        --mcpo-port)
            export GOFR_DIG_MCPO_PORT="$2"
            shift 2
            ;;
        --mcpo-host)
            export GOFR_DIG_MCPO_HOST="$2"
            shift 2
            ;;
        --web-port)
            export GOFR_DIG_WEB_PORT="$2"
            shift 2
            ;;
        --web-host)
            export GOFR_DIG_WEB_HOST="$2"
            shift 2
            ;;
        --kill-all|--help)
            PASSTHROUGH_ARGS+=("$1")
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Unset data-related vars so they get recalculated based on GOFR_DIG_ENV
unset GOFR_DIG_DATA GOFR_DIG_STORAGE

# Re-source after env vars may have changed
source "$SCRIPT_DIR/gofr-dig.env"

# Map project-specific vars to common vars
export GOFR_PROJECT_NAME="gofr-dig"
export GOFR_PROJECT_ROOT="$GOFR_DIG_ROOT"
export GOFR_LOGS_DIR="$GOFR_DIG_LOGS"
export GOFR_DATA_DIR="$GOFR_DIG_DATA"
export GOFR_ENV="$GOFR_DIG_ENV"
export GOFR_MCP_PORT="$GOFR_DIG_MCP_PORT"
export GOFR_MCPO_PORT="$GOFR_DIG_MCPO_PORT"
export GOFR_WEB_PORT="$GOFR_DIG_WEB_PORT"
export GOFR_MCP_HOST="$GOFR_DIG_MCP_HOST"
export GOFR_MCPO_HOST="$GOFR_DIG_MCPO_HOST"
export GOFR_WEB_HOST="$GOFR_DIG_WEB_HOST"
export GOFR_NETWORK="$GOFR_DIG_NETWORK"

# Call shared script
source "$COMMON_SCRIPTS/restart_servers.sh" "${PASSTHROUGH_ARGS[@]}"
