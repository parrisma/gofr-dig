#!/bin/bash
# Wrapper script to restore a backup for gofr-dig

set -e

# Set project identifier
export GOFR_PROJECT=dig

# Locate and execute the shared backup script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_SCRIPT="$SCRIPT_DIR/../lib/gofr-common/scripts/backup/restore_backup.sh"

if [ ! -f "$SHARED_SCRIPT" ]; then
    echo "Error: Shared backup script not found at $SHARED_SCRIPT"
    echo "Please ensure gofr-common submodule is initialized: git submodule update --init"
    exit 1
fi

exec "$SHARED_SCRIPT" "$@"
