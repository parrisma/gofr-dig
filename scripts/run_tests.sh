#!/bin/bash
# =============================================================================
# GOFR-Dig Test Runner
# =============================================================================
# Standardized test runner script for the gofr-dig project.
#
# Integration tests require running MCP/Web/MCPO services. This script uses
# scripts/start-test-env.sh to launch ephemeral Docker services on test ports
# (test ports from gofr_ports.env: MCP/MCPO/Web) via compose.dev.yml.
#
# Usage:
#   ./scripts/run_tests.sh                          # Run all tests (with servers)
#   ./scripts/run_tests.sh test/mcp/                # Run specific test directory
#   ./scripts/run_tests.sh -k "dig"                 # Run tests matching keyword
#   ./scripts/run_tests.sh -v                       # Run with verbose output
#   ./scripts/run_tests.sh --coverage               # Run with coverage report
#   ./scripts/run_tests.sh --coverage-html          # Run with HTML coverage report
#   ./scripts/run_tests.sh --integration            # Run integration tests only (with servers)
#   ./scripts/run_tests.sh --no-servers             # Run without starting servers
#   ./scripts/run_tests.sh --stop                   # Stop servers only
#   ./scripts/run_tests.sh --cleanup-only           # Clean environment only
# =============================================================================

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# =============================================================================
# CONFIGURATION
# =============================================================================

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project-specific configuration
PROJECT_NAME="gofr-dig"
TEST_DIR="test"
COVERAGE_SOURCE="app"
LOG_DIR="${PROJECT_ROOT}/logs"
START_DEV_SCRIPT="${PROJECT_ROOT}/scripts/start-test-env.sh"

# Activate virtual environment
VENV_DIR="${PROJECT_ROOT}/.venv"
if [ -f "${VENV_DIR}/bin/activate" ]; then
    source "${VENV_DIR}/bin/activate"
    echo "Activated venv: ${VENV_DIR}"
else
    echo -e "${YELLOW}Warning: Virtual environment not found at ${VENV_DIR}${NC}"
fi

# Source centralized environment configuration
export GOFR_DIG_ENV="TEST"
if [ -f "${SCRIPT_DIR}/gofr-dig.env" ]; then
    source "${SCRIPT_DIR}/gofr-dig.env"
fi

# Load centralized port config (single source of truth)
PORTS_ENV="${PROJECT_ROOT}/lib/gofr-common/config/gofr_ports.env"
if [ -f "${PORTS_ENV}" ]; then
    source "${PORTS_ENV}"
fi

# Set up PYTHONPATH for gofr-common discovery
if [ -d "${PROJECT_ROOT}/lib/gofr-common/src" ]; then
    export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/lib/gofr-common/src:${PYTHONPATH:-}"
elif [ -d "${PROJECT_ROOT}/../gofr-common/src" ]; then
    export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/../gofr-common/src:${PYTHONPATH:-}"
else
    export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"
fi

# Test configuration
export GOFR_JWT_SECRET="test-secret-key-for-secure-testing-do-not-use-in-production"
export GOFR_DIG_AUTH_BACKEND="vault"
# Test ports come from gofr_ports.env (sourced above) — no hardcoded fallbacks
export GOFR_DIG_MCP_PORT_TEST="${GOFR_DIG_MCP_PORT_TEST:?GOFR_DIG_MCP_PORT_TEST not set — source gofr_ports.env}"
export GOFR_DIG_MCPO_PORT_TEST="${GOFR_DIG_MCPO_PORT_TEST:?GOFR_DIG_MCPO_PORT_TEST not set — source gofr_ports.env}"
export GOFR_DIG_WEB_PORT_TEST="${GOFR_DIG_WEB_PORT_TEST:?GOFR_DIG_WEB_PORT_TEST not set — source gofr_ports.env}"

# Save original container-internal (prod) ports before overwriting with test ports.
# Docker containers listen on these prod ports; port mapping only applies on host.
_GOFR_DIG_MCP_PORT_INTERNAL="${GOFR_DIG_MCP_PORT}"
_GOFR_DIG_MCPO_PORT_INTERNAL="${GOFR_DIG_MCPO_PORT}"
_GOFR_DIG_WEB_PORT_INTERNAL="${GOFR_DIG_WEB_PORT}"

# Docker vs localhost addressing — set after argument parsing (see apply_docker_mode below)
# Defaults are overridden by --docker / --no-docker flags
export GOFR_DIG_HOST="${GOFR_DIG_HOST:-localhost}"
export GOFR_DIG_MCP_PORT="${GOFR_DIG_MCP_PORT_TEST}"
export GOFR_DIG_MCPO_PORT="${GOFR_DIG_MCPO_PORT_TEST}"
export GOFR_DIG_WEB_PORT="${GOFR_DIG_WEB_PORT_TEST}"

# Ensure directories exist
mkdir -p "${LOG_DIR}"
mkdir -p "${GOFR_DIG_STORAGE:-${PROJECT_ROOT}/data/storage}"

# Vault test configuration
VAULT_CONTAINER_NAME="gofr-vault-test"
VAULT_IMAGE="hashicorp/vault:1.15.4"
VAULT_INTERNAL_PORT=8200
VAULT_TEST_PORT="${GOFR_VAULT_PORT_TEST:?GOFR_VAULT_PORT_TEST not set — source gofr_ports.env}"
VAULT_TEST_TOKEN="${GOFR_TEST_VAULT_DEV_TOKEN:-gofr-dev-root-token}"
TEST_NETWORK="${GOFR_TEST_NETWORK:-gofr-test-net}"
DEV_CONTAINER_NAMES=("gofr-dig-dev")

# Test-only secrets volume (isolated from production secrets)
SECRETS_TEST_VOLUME="gofr-secrets-test"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

print_header() {
    echo -e "${GREEN}=== ${PROJECT_NAME} Test Runner ===${NC}"
    echo "Project root: ${PROJECT_ROOT}"
    echo "Environment: ${GOFR_DIG_ENV}"
    if [ "$USE_DOCKER" = true ]; then
        echo "Addressing: Docker hostnames (container network)"
    else
        echo "Addressing: localhost (published ports)"
    fi
    echo "MCP URL:  ${GOFR_DIG_MCP_URL}"
    echo "MCPO URL: ${GOFR_DIG_MCPO_URL}"
    echo "Web URL:  ${GOFR_DIG_WEB_URL}"
    echo ""
}

start_services() {
    echo -e "${GREEN}=== Starting Ephemeral Docker Services ===${NC}"
    if [ ! -x "${START_DEV_SCRIPT}" ]; then
        echo -e "${RED}start-test-env.sh not found or not executable: ${START_DEV_SCRIPT}${NC}"
        exit 1
    fi
    "${START_DEV_SCRIPT}" --build
    echo ""
}

stop_services() {
    echo -e "${YELLOW}Stopping ephemeral Docker services...${NC}"
    if [ -x "${START_DEV_SCRIPT}" ]; then
        "${START_DEV_SCRIPT}" --down 2>/dev/null || true
    fi
    echo -e "${GREEN}Services stopped${NC}"
}

cleanup_environment() {
    echo -e "${YELLOW}Cleaning up test environment...${NC}"
    stop_services
    stop_vault_test_container
    echo -e "${GREEN}Cleanup complete${NC}"
}

run_code_quality_gate() {
    echo -e "${BLUE}Running code quality gate...${NC}"
    set +e
    uv run python -m pytest ${TEST_DIR}/code_quality/test_code_quality.py -v
    local gate_exit_code=$?
    set -e

    if [ $gate_exit_code -ne 0 ]; then
        echo -e "${RED}ALL Code quality issues must be solved before running other tests${NC}"
        exit $gate_exit_code
    fi
}

start_vault_test_container() {
    echo -e "${BLUE}Starting Vault in ephemeral dev mode...${NC}"

    is_running_in_docker() {
        [ -f "/.dockerenv" ] && return 0
        grep -qa "docker\|containerd" /proc/1/cgroup 2>/dev/null && return 0
        return 1
    }

    if ! docker network ls --format '{{.Name}}' | grep -q "^${TEST_NETWORK}$"; then
        echo "Creating test network: ${TEST_NETWORK}"
        docker network create "${TEST_NETWORK}"
    fi

    # Create test-only secrets volume (isolated from production gofr-secrets)
    if ! docker volume inspect "${SECRETS_TEST_VOLUME}" >/dev/null 2>&1; then
        echo "Creating test secrets volume: ${SECRETS_TEST_VOLUME}"
        docker volume create "${SECRETS_TEST_VOLUME}"
    fi

    for dev_name in "${DEV_CONTAINER_NAMES[@]}"; do
        if docker ps --format '{{.Names}}' | grep -q "^${dev_name}$"; then
            if ! docker network inspect "${TEST_NETWORK}" --format '{{range .Containers}}{{.Name}} {{end}}' | grep -q "${dev_name}"; then
                echo "Connecting ${dev_name} to ${TEST_NETWORK}..."
                docker network connect "${TEST_NETWORK}" "${dev_name}" 2>/dev/null || true
            fi
        fi
    done

    if ! docker images "${VAULT_IMAGE}" --format '{{.Repository}}' | grep -q "vault"; then
        echo -e "${YELLOW}Pulling Vault image: ${VAULT_IMAGE}${NC}"
        docker pull "${VAULT_IMAGE}"
    fi

    if docker ps -aq -f name="^${VAULT_CONTAINER_NAME}$" | grep -q .; then
        echo "Removing existing Vault test container..."
        docker rm -f "${VAULT_CONTAINER_NAME}" 2>/dev/null || true
    fi

    echo "Starting ${VAULT_CONTAINER_NAME} (dev mode, port ${VAULT_TEST_PORT}->${VAULT_INTERNAL_PORT})..."
    docker run -d \
        --name "${VAULT_CONTAINER_NAME}" \
        --hostname "${VAULT_CONTAINER_NAME}" \
        --network "${TEST_NETWORK}" \
        --cap-add IPC_LOCK \
        -p "${VAULT_TEST_PORT}:${VAULT_INTERNAL_PORT}" \
        -e "VAULT_DEV_ROOT_TOKEN_ID=${VAULT_TEST_TOKEN}" \
        -e "VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:${VAULT_INTERNAL_PORT}" \
        -e "VAULT_LOG_LEVEL=warn" \
        "${VAULT_IMAGE}" \
        server -dev > /dev/null

    echo -n "Waiting for Vault to be ready"
    local retries=0
    local max_retries=30
    while [ $retries -lt $max_retries ]; do
        if docker exec -e VAULT_ADDR="http://127.0.0.1:${VAULT_INTERNAL_PORT}" \
            "${VAULT_CONTAINER_NAME}" vault status > /dev/null 2>&1; then
            echo " ready!"
            break
        fi
        echo -n "."
        sleep 1
        retries=$((retries + 1))
    done
    if [ $retries -eq $max_retries ]; then
        echo ""
        echo -e "${RED}Vault failed to start within ${max_retries}s${NC}"
        docker logs "${VAULT_CONTAINER_NAME}" 2>&1
        return 1
    fi

    docker exec -e VAULT_ADDR="http://127.0.0.1:${VAULT_INTERNAL_PORT}" \
        -e VAULT_TOKEN="${VAULT_TEST_TOKEN}" \
        "${VAULT_CONTAINER_NAME}" \
        vault secrets enable -path=secret -version=2 kv 2>/dev/null || true

    # Vault access for the pytest process.
    # In Docker mode, pytest runs in the dev container and should talk to Vault
    # via the container hostname on the shared test network.
    if is_running_in_docker; then
        export GOFR_DIG_VAULT_URL="http://${VAULT_CONTAINER_NAME}:${VAULT_INTERNAL_PORT}"

        # Fail fast if Docker DNS is not available (prevents flaky mid-suite failures).
        if ! getent hosts "${VAULT_CONTAINER_NAME}" > /dev/null 2>&1; then
            echo -e "${RED}FATAL: Cannot resolve ${VAULT_CONTAINER_NAME} from the test runner.${NC}"
            echo "Expected: dev container attached to '${TEST_NETWORK}' so Docker DNS can resolve service names."
            echo "Try: docker network connect ${TEST_NETWORK} gofr-dig-dev"
            return 1
        fi
    else
        # Localhost mode: use the published test port.
        export GOFR_DIG_VAULT_URL="http://127.0.0.1:${VAULT_TEST_PORT}"
    fi
    export GOFR_DIG_VAULT_TOKEN="${VAULT_TEST_TOKEN}"

    echo -e "${GREEN}Vault started successfully${NC}"
    echo "  Container: ${VAULT_CONTAINER_NAME}"
    echo "  Network:   ${TEST_NETWORK}"
    echo "  URL:       ${GOFR_DIG_VAULT_URL}"
    echo "  Token:     ${GOFR_DIG_VAULT_TOKEN}"
    echo ""
}

stop_vault_test_container() {
    echo -e "${YELLOW}Stopping Vault test container...${NC}"
    if docker ps -q -f name="^${VAULT_CONTAINER_NAME}$" | grep -q .; then
        docker stop ${VAULT_CONTAINER_NAME} 2>/dev/null || true
        docker rm ${VAULT_CONTAINER_NAME} 2>/dev/null || true
        echo -e "${GREEN}Vault container stopped${NC}"
    else
        echo "Vault container was not running"
    fi

    for dev_name in "${DEV_CONTAINER_NAMES[@]}"; do
        if docker ps --format '{{.Names}}' | grep -q "^${dev_name}$"; then
            docker network disconnect "${TEST_NETWORK}" "${dev_name}" 2>/dev/null || true
        fi
    done
}

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

START_SERVERS=true
COVERAGE=false
COVERAGE_HTML=false
RUN_INTEGRATION=false
RUN_ALL=false
RUN_SIMULATOR=false
STOP_ONLY=false
CLEANUP_ONLY=false
USE_DOCKER=true   # Default: use Docker container hostnames for integration tests
PYTEST_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --coverage|--cov)
            COVERAGE=true
            shift
            ;;
        --coverage-html)
            COVERAGE=true
            COVERAGE_HTML=true
            shift
            ;;
        --integration)
            RUN_INTEGRATION=true
            START_SERVERS=true
            shift
            ;;
        --simulator)
            RUN_SIMULATOR=true
            START_SERVERS=false
            shift
            ;;
        --all)
            RUN_ALL=true
            START_SERVERS=true
            shift
            ;;
        --no-servers|--without-servers)
            START_SERVERS=false
            shift
            ;;
        --docker)
            USE_DOCKER=true
            shift
            ;;
        --no-docker)
            USE_DOCKER=false
            shift
            ;;
        --with-servers|--start-servers)
            START_SERVERS=true
            shift
            ;;
        --stop|--stop-servers)
            STOP_ONLY=true
            shift
            ;;
        --cleanup-only)
            CLEANUP_ONLY=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS] [PYTEST_ARGS...]"
            echo ""
            echo "Options:"
            echo "  --coverage       Run with coverage report"
            echo "  --coverage-html  Run with HTML coverage report"
            echo "  --integration    Run integration tests only (with servers)"
            echo "  --simulator      Run simulator tests only (no servers needed)"
            echo "  --all            Run all test categories"
            echo "  --docker         Use Docker hostnames for integration tests (default)"
            echo "  --no-docker      Use localhost+published ports for integration tests"
            echo "  --no-servers     Don't start Docker services"
            echo "  --with-servers   Start Docker services (default)"
            echo "  --stop           Stop Docker services and exit"
            echo "  --cleanup-only   Clean environment and exit"
            echo "  --help, -h       Show this help message"
            exit 0
            ;;
        *)
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# =============================================================================
# APPLY DOCKER / LOCALHOST ADDRESSING MODE
# =============================================================================

if [ "$USE_DOCKER" = true ]; then
    # Docker mode: use container hostnames + internal (prod) ports.
    # The dev container and test containers share gofr-test-net.
    # Containers listen on prod ports internally (8070/8071/8072);
    # port mapping (e.g. 8170→8070) only applies to host access.
    export GOFR_DIG_HOST="gofr-dig-mcp-test"
    export GOFR_DIG_MCP_PORT="${_GOFR_DIG_MCP_PORT_INTERNAL}"
    export GOFR_DIG_MCPO_PORT="${_GOFR_DIG_MCPO_PORT_INTERNAL}"
    export GOFR_DIG_WEB_PORT="${_GOFR_DIG_WEB_PORT_INTERNAL}"

    # Full URLs for integration tests (container hostname + internal prod port)
    export GOFR_DIG_MCP_URL="http://gofr-dig-mcp-test:${_GOFR_DIG_MCP_PORT_INTERNAL}/mcp"
    export GOFR_DIG_MCPO_URL="http://gofr-dig-mcpo-test:${_GOFR_DIG_MCPO_PORT_INTERNAL}"
    export GOFR_DIG_WEB_URL="http://gofr-dig-web-test:${_GOFR_DIG_WEB_PORT_INTERNAL}"

    # Fixture server: bind to 0.0.0.0 so test containers can reach it.
    # Use dev container hostname on the shared network.
    export GOFR_DIG_FIXTURE_HOST="0.0.0.0"
    export GOFR_DIG_FIXTURE_EXTERNAL_HOST="gofr-dig-dev"
else
    # Localhost mode: use published test ports (prod + 100).
    export GOFR_DIG_HOST="localhost"
    export GOFR_DIG_MCP_PORT="${GOFR_DIG_MCP_PORT_TEST}"
    export GOFR_DIG_MCPO_PORT="${GOFR_DIG_MCPO_PORT_TEST}"
    export GOFR_DIG_WEB_PORT="${GOFR_DIG_WEB_PORT_TEST}"

    export GOFR_DIG_MCP_URL="http://localhost:${GOFR_DIG_MCP_PORT}/mcp"
    export GOFR_DIG_MCPO_URL="http://localhost:${GOFR_DIG_MCPO_PORT}"
    export GOFR_DIG_WEB_URL="http://localhost:${GOFR_DIG_WEB_PORT}"

    export GOFR_DIG_FIXTURE_HOST="127.0.0.1"
    export GOFR_DIG_FIXTURE_EXTERNAL_HOST="127.0.0.1"
fi

# =============================================================================
# MAIN EXECUTION
# =============================================================================

print_header

# Handle stop-only mode
if [ "$STOP_ONLY" = true ]; then
    echo -e "${YELLOW}Stopping services and exiting...${NC}"
    stop_services
    exit 0
fi

# Handle cleanup-only mode
if [ "$CLEANUP_ONLY" = true ]; then
    cleanup_environment
    exit 0
fi

# Fail-fast quality gate before starting services and running other tests
run_code_quality_gate

# Start Vault for tests
start_vault_test_container
trap 'stop_vault_test_container' EXIT

# Start Docker services if needed
if [ "$START_SERVERS" = true ]; then
    start_services
fi

# Build coverage arguments
COVERAGE_ARGS=""
if [ "$COVERAGE" = true ]; then
    COVERAGE_ARGS="--cov=${COVERAGE_SOURCE} --cov-report=term-missing"
    if [ "$COVERAGE_HTML" = true ]; then
        COVERAGE_ARGS="${COVERAGE_ARGS} --cov-report=html:htmlcov"
    fi
    echo -e "${BLUE}Coverage reporting enabled${NC}"
fi

# =============================================================================
# RUN TESTS
# =============================================================================

echo -e "${GREEN}=== Running Tests ===${NC}"
set +e
TEST_EXIT_CODE=0

if [ "$RUN_INTEGRATION" = true ]; then
    echo -e "${BLUE}Running integration tests (with servers)...${NC}"
    uv run python -m pytest ${TEST_DIR}/integration/ -v ${COVERAGE_ARGS}
    TEST_EXIT_CODE=$?

elif [ "$RUN_SIMULATOR" = true ]; then
    echo -e "${BLUE}Running simulator tests (no servers)...${NC}"
    uv run python -m pytest ${TEST_DIR}/simulator/ -v ${COVERAGE_ARGS}
    TEST_EXIT_CODE=$?

elif [ "$RUN_ALL" = true ]; then
    echo -e "${BLUE}Running ALL tests...${NC}"
    uv run python -m pytest ${TEST_DIR}/ -v ${COVERAGE_ARGS}
    TEST_EXIT_CODE=$?

elif [ ${#PYTEST_ARGS[@]} -eq 0 ]; then
    # Default: run all tests
    uv run python -m pytest ${TEST_DIR}/ -v ${COVERAGE_ARGS}
    TEST_EXIT_CODE=$?
else
    # Custom arguments
    uv run python -m pytest "${PYTEST_ARGS[@]}" ${COVERAGE_ARGS}
    TEST_EXIT_CODE=$?
fi
set -e

# =============================================================================
# CLEANUP
# =============================================================================

if [ "$START_SERVERS" = true ]; then
    echo ""
    stop_services
fi

# =============================================================================
# RESULTS
# =============================================================================

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}=== Tests Passed ===${NC}"
    if [ "$COVERAGE" = true ] && [ "$COVERAGE_HTML" = true ]; then
        echo -e "${BLUE}HTML coverage report: ${PROJECT_ROOT}/htmlcov/index.html${NC}"
    fi
else
    echo -e "${RED}=== Tests Failed (exit code: ${TEST_EXIT_CODE}) ===${NC}"
    echo "Docker service logs:"
    echo "  docker compose -f docker/compose.dev.yml logs"
fi

exit $TEST_EXIT_CODE
