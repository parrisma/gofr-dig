#!/usr/bin/env bash
set -euo pipefail

# Run Trivy-based vulnerability scan through gofr-common shared module.
# Usage:
#   ./scripts/scan_container_security.sh <image-ref> [env-prefix]
# Example:
#   ./scripts/scan_container_security.sh gofr-dig-prod:latest GOFR_DIG

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <image-ref> [env-prefix]"
  exit 1
fi

IMAGE_REF="$1"
ENV_PREFIX="${2:-GOFR_DIG}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

uv run --project lib/gofr-common python -m gofr_common.security_scan.cli --image "${IMAGE_REF}" --env-prefix "${ENV_PREFIX}"
