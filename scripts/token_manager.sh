#!/bin/bash
# Token manager script for GOFR-DIG
# Wraps the Python token_manager module

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source centralized configuration
source "$SCRIPT_DIR/gofr-dig.env"

# Parse environment argument if provided
while [[ $# -gt 0 ]]; do
    case "$1" in
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

# Run token manager with correct paths
cd "$GOFR_DIG_ROOT"
uv run python -m app.auth.token_manager \
    --gofr-dig-env "$GOFR_DIG_ENV" \
    --token-store "$GOFR_DIG_TOKEN_STORE" \
    "$@"
