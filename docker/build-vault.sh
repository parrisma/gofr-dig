#!/bin/bash
# Build the shared GOFR Vault image from gofr-common
# Image: gofr-vault:latest

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMMON_ROOT="$PROJECT_ROOT/lib/gofr-common"

echo "======================================================================="
echo "Building GOFR Vault Image"
echo "======================================================================="

# Verify gofr-common exists with the Dockerfile
if [ ! -f "$COMMON_ROOT/docker/Dockerfile.vault" ]; then
    echo "Error: Dockerfile.vault not found at $COMMON_ROOT/docker/Dockerfile.vault"
    exit 1
fi

echo ""
echo "Building gofr-vault:latest..."

# Create a temporary Dockerfile that works without BuildKit
# (The original uses --chmod which requires BuildKit)
TEMP_DOCKERFILE=$(mktemp)
cat > "$TEMP_DOCKERFILE" << 'EOF'
FROM hashicorp/vault:1.15.4

ARG BUILD_DATE
ARG GIT_COMMIT
LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.version="1.15.4" \
      org.opencontainers.image.title="gofr-vault" \
      org.opencontainers.image.description="HashiCorp Vault for GOFR infrastructure"

COPY docker/vault-config.hcl /vault/config/vault.hcl
COPY docker/entrypoint-vault.sh /entrypoint-vault.sh
RUN chmod 755 /entrypoint-vault.sh

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD vault status || exit 1

EXPOSE 8201 8202

ENTRYPOINT ["/entrypoint-vault.sh"]
CMD ["server", "-config=/vault/config/vault.hcl"]
EOF

docker build \
    -f "$TEMP_DOCKERFILE" \
    -t gofr-vault:latest \
    --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --build-arg GIT_COMMIT="$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)" \
    "$COMMON_ROOT"

rm -f "$TEMP_DOCKERFILE"

echo ""
echo "======================================================================="
echo "Build complete: gofr-vault:latest"
echo "======================================================================="
echo ""
echo "Image size:"
docker images gofr-vault:latest --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
echo ""
echo "Next steps:"
echo "  ../lib/gofr-common/scripts/manage_vault.sh start     # Start Vault"
echo "  ../lib/gofr-common/scripts/manage_vault.sh bootstrap  # Full init + unseal + auth"
