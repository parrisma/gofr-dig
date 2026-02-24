#!/bin/bash
set -euo pipefail

# Standard GOFR user paths - all projects use 'gofr' user
GOFR_USER="gofr"
PROJECT_DIR="/home/${GOFR_USER}/devroot/gofr-dig"
# gofr-common is now a git submodule in lib/gofr-common
COMMON_DIR="$PROJECT_DIR/lib/gofr-common"
VENV_DIR="$PROJECT_DIR/.venv"

echo "======================================================================="
echo "GOFR-DIG Container Entrypoint"
echo "======================================================================="

# -----------------------------------------------------------------------
# Map unknown host GIDs into /etc/group so 'groups' does not warn.
# The container runs with --user UID:GID from the host; those GIDs may
# not exist inside the image.
# -----------------------------------------------------------------------
for _gid in $(id -G 2>/dev/null); do
    if ! getent group "$_gid" >/dev/null 2>&1; then
        sudo groupadd -g "$_gid" "hostgroup_${_gid}" 2>/dev/null || true
    fi
done
unset _gid

ensure_dir() {
    local dir="$1"
    if [ -d "$dir" ]; then
        return 0
    fi
    mkdir -p "$dir" 2>/dev/null || sudo mkdir -p "$dir" 2>/dev/null
}

# Fix Docker socket GID mismatch (silence "cannot find name for group ID" warning)
# When --group-add GID is used, the numeric GID may not have a name in /etc/group
if [ -S /var/run/docker.sock ]; then
    DOCKER_SOCK_GID=$(stat -c '%g' /var/run/docker.sock)
    if ! getent group "$DOCKER_SOCK_GID" >/dev/null 2>&1; then
        echo "Creating docker group with GID $DOCKER_SOCK_GID to match host socket..."
        sudo groupadd -g "$DOCKER_SOCK_GID" docker 2>/dev/null || true
        sudo usermod -aG docker "$GOFR_USER" 2>/dev/null || true
    fi
fi

# Fix data directory permissions if mounted as volume
if [ -d "$PROJECT_DIR/data" ]; then
    if [ ! -w "$PROJECT_DIR/data" ]; then
        echo "Fixing permissions for $PROJECT_DIR/data..."
        sudo chown -R "$(id -u):$(id -g)" "$PROJECT_DIR/data" 2>/dev/null || \
            echo "Warning: Could not fix permissions. Run container with --user $(id -u):$(id -g)"
    fi
fi

# Create subdirectories if they don't exist
if ! ensure_dir "$PROJECT_DIR/data/storage"; then
    echo "Warning: Could not create $PROJECT_DIR/data/storage"
fi
if ! ensure_dir "$PROJECT_DIR/data/auth"; then
    echo "Warning: Could not create $PROJECT_DIR/data/auth"
fi
if ! ensure_dir "$PROJECT_DIR/logs"; then
    echo "Warning: Could not create $PROJECT_DIR/logs (bind mount may be read-only for this UID/GID)"
fi

# Ensure virtual environment exists and is valid
if [ ! -f "$VENV_DIR/bin/python" ] || [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "Creating Python virtual environment..."
    cd "$PROJECT_DIR"
    UV_VENV_CLEAR=1 uv venv "$VENV_DIR" --python=python3.11
    echo "Virtual environment created at $VENV_DIR"
fi

# Install gofr-common as editable package
if [ -f "$COMMON_DIR/pyproject.toml" ]; then
    echo "Installing gofr-common (editable)..."
    cd "$PROJECT_DIR"
    uv pip install -e "$COMMON_DIR"
else
    echo ""
    echo "ERROR: gofr-common is not initialised at $COMMON_DIR"
    echo "  The directory exists but has no pyproject.toml."
    echo "  This usually means the git submodule was not initialised."
    echo ""
    echo "  Fix (run from the project root on the host):"
    echo "    git submodule update --init --recursive"
    echo ""
    exit 1
fi

# Install project dependencies
if [ -f "$PROJECT_DIR/pyproject.toml" ]; then
    echo "Installing project dependencies from pyproject.toml..."
    cd "$PROJECT_DIR"
    uv pip install -e ".[dev]" || echo "Warning: Could not install project dependencies"
fi

# Show installed packages
echo ""
echo "Environment ready. Installed packages:"
uv pip list

echo ""
echo "======================================================================="
echo "Entrypoint complete. Executing: $@"
echo "======================================================================="

exec "$@"
