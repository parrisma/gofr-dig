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

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_FILE="$SCRIPT_DIR/project.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: environment file not found: $ENV_FILE" >&2
    exit 1
fi

# Source centralized configuration (defaults to TEST)
source "$ENV_FILE"

# Parse --env flag if provided as first argument
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            if [[ $# -lt 2 ]]; then
                echo "Error: --env requires a value (PROD or TEST)" >&2
                exit 1
            fi
            if [[ "$2" != "PROD" && "$2" != "TEST" ]]; then
                echo "Error: invalid --env value '$2' (allowed: PROD, TEST)" >&2
                exit 1
            fi
            export GOFR_DIG_ENV="$2"
            shift 2
            ;;
        *)
            break
            ;;
    esac
done

# Re-source project.env with potentially updated GOFR_DIG_ENV to pick up correct paths
source "$ENV_FILE"

if [[ -z "${GOFR_DIG_ROOT:-}" ]]; then
    echo "Error: GOFR_DIG_ROOT is not set after sourcing $ENV_FILE" >&2
    exit 1
fi

if [[ -z "${GOFR_DIG_DATA:-}" || -z "${GOFR_DIG_STORAGE:-}" ]]; then
    echo "Error: GOFR_DIG_DATA and GOFR_DIG_STORAGE must be set after sourcing $ENV_FILE" >&2
    exit 1
fi

if [[ $# -eq 0 ]]; then
    echo "Error: missing command (e.g. list, stats, purge, prune-size)" >&2
    exit 1
fi

# Call Python module with environment variables as CLI args
cd "$GOFR_DIG_ROOT"
uv run python -m app.management.storage_manager \
    --gofr-dig-env "$GOFR_DIG_ENV" \
    --data-root "$GOFR_DIG_DATA" \
    --storage-dir "$GOFR_DIG_STORAGE" \
    "$@"
