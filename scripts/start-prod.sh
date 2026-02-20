#!/bin/bash
# Compatibility shim: the canonical prod lifecycle scripts are now in docker/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

exec bash "$PROJECT_ROOT/docker/start-prod.sh" "$@"
