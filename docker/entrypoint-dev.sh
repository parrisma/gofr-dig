#!/bin/bash
set -e

PROJECT_DIR="/home/gofr/devroot/gofr-dig"
VENV_DIR="$PROJECT_DIR/.venv"

# Fix data directory permissions if mounted as volume
if [ -d "$PROJECT_DIR/data" ]; then
    # Check if we can write to data directory
    if [ ! -w "$PROJECT_DIR/data" ]; then
        echo "Fixing permissions for $PROJECT_DIR/data..."
        # This will work if container is started with appropriate privileges
        sudo chown -R gofr:gofr "$PROJECT_DIR/data" 2>/dev/null || \
            echo "Warning: Could not fix permissions. Run container with --user $(id -u):$(id -g)"
    fi
fi

# Create subdirectories if they don't exist
mkdir -p "$PROJECT_DIR/data/storage" "$PROJECT_DIR/data/auth"
mkdir -p "$PROJECT_DIR/logs"

# Create virtual environment if it doesn't exist or is corrupted
# (Source mount overwrites the venv created during docker build)
if [ ! -f "$VENV_DIR/bin/python" ] || [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "Creating Python virtual environment..."
    cd "$PROJECT_DIR"
    rm -rf "$VENV_DIR" 2>/dev/null || true
    uv venv "$VENV_DIR" --python=python3.11
    echo "Virtual environment created at $VENV_DIR"
fi

# Install/sync Python dependencies
cd "$PROJECT_DIR"
if [ -f "$PROJECT_DIR/pyproject.toml" ]; then
    echo "Installing Python dependencies from pyproject.toml..."
    VIRTUAL_ENV="$VENV_DIR" uv pip install -e ".[dev]" || \
        echo "Warning: Could not install dependencies from pyproject.toml"
elif [ -f "$PROJECT_DIR/requirements.txt" ]; then
    echo "Installing Python dependencies from requirements.txt..."
    VIRTUAL_ENV="$VENV_DIR" uv pip install -r requirements.txt || \
        echo "Warning: Could not install dependencies"
fi

# Execute the main command
exec "$@"
