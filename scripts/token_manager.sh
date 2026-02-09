#!/bin/bash
# GOFR-DIG Token Manager
# Wrapper for the shared token_manager.sh script
#
# Usage: ./token_manager.sh [--env PROD|TEST] <command> [options]
#
# Commands:
#   create    Create a new token
#   list      List all tokens
#   verify    Verify a token
#   revoke    Revoke a token

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_SCRIPTS="$SCRIPT_DIR/../../gofr-common/scripts"

# Check for lib/gofr-common location first (inside container)
if [ -d "$SCRIPT_DIR/../lib/gofr-common/scripts" ]; then
    COMMON_SCRIPTS="$SCRIPT_DIR/../lib/gofr-common/scripts"
fi

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

# Re-source gofr-dig.env with potentially updated GOFR_DIG_ENV
source "$SCRIPT_DIR/gofr-dig.env"

echo "ERROR: token_manager.sh is deprecated. Use lib/gofr-common/scripts/auth_manager.sh instead." >&2
echo "Example: lib/gofr-common/scripts/auth_manager.sh --docker tokens list" >&2
exit 1
