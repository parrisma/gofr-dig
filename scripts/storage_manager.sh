#!/bin/bash
# Storage Manager CLI Wrapper for gofr-dig
# Provides environment-aware access to storage and sessions management
#
# Usage:
#   ./storage_manager.sh [--env PROD|TEST] <command> [options]
#
# Examples:
#   ./storage_manager.sh list                         # Uses current GOFR_DIG_ENV
#   ./storage_manager.sh --env PROD stats             # Force PROD environment
#   ./storage_manager.sh --env TEST purge --yes       # Force TEST environment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source centralized configuration (defaults to TEST)
source "$SCRIPT_DIR/gofr-dig.env"

# Parse --env flag if provided as first argument
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            export GOFR_DIG_ENV="$2"
            shift 2
            ;;
        *)
            break
            ;;
    esac
done

# Re-source gofr-dig.env with potentially updated GOFR_DIG_ENV to pick up correct paths
source "$SCRIPT_DIR/gofr-dig.env"

# Call Python module with environment variables as CLI args
cd "$GOFR_DIG_ROOT"
uv run python -m app.management.storage_manager \
    --gofr-dig-env "$GOFR_DIG_ENV" \
    --data-root "$GOFR_DIG_DATA" \
    --storage-dir "$GOFR_DIG_STORAGE" \
    "$@"
