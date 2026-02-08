#!/bin/bash
# =============================================================================
# GOFR-Dig Test Runner
# =============================================================================
# Standardized test runner script for the gofr-dig project.
#
# Integration tests require running MCP/Web/MCPO services. This script uses
# docker/start-dev.sh to launch ephemeral Docker services on test ports
# (prod + 100: MCP=8170, MCPO=8171, Web=8172) via compose.dev.yml.
#
# Usage:
#   ./scripts/run_tests.sh                          # Run all tests (with servers)
#   ./scripts/run_tests.sh test/mcp/                # Run specific test directory
#   ./scripts/run_tests.sh -k "dig"                 # Run tests matching keyword
#   ./scripts/run_tests.sh -v                       # Run with verbose output
#   ./scripts/run_tests.sh --coverage               # Run with coverage report
#   ./scripts/run_tests.sh --coverage-html          # Run with HTML coverage report
#   ./scripts/run_tests.sh --unit                   # Run unit tests only (no servers)
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
START_DEV_SCRIPT="${PROJECT_ROOT}/docker/start-dev.sh"

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

# Test configuration — use test ports (prod + 100) from centralized config
export GOFR_DIG_JWT_SECRET="test-secret-key-for-secure-testing-do-not-use-in-production"
export GOFR_DIG_TOKEN_STORE="${LOG_DIR}/${PROJECT_NAME}_tokens_test.json"
export GOFR_DIG_AUTH_BACKEND="${GOFR_DIG_AUTH_BACKEND:-memory}"
export GOFR_DIG_HOST="${GOFR_DIG_HOST:-localhost}"
export GOFR_DIG_MCP_PORT="${GOFR_DIG_MCP_PORT_TEST:-8170}"
export GOFR_DIG_MCPO_PORT="${GOFR_DIG_MCPO_PORT_TEST:-8171}"
export GOFR_DIG_WEB_PORT="${GOFR_DIG_WEB_PORT_TEST:-8172}"
# Also export _TEST vars so integration tests pick them up directly
export GOFR_DIG_MCP_PORT_TEST="${GOFR_DIG_MCP_PORT_TEST:-8170}"
export GOFR_DIG_MCPO_PORT_TEST="${GOFR_DIG_MCPO_PORT_TEST:-8171}"
export GOFR_DIG_WEB_PORT_TEST="${GOFR_DIG_WEB_PORT_TEST:-8172}"

# Ensure directories exist
mkdir -p "${LOG_DIR}"
mkdir -p "${GOFR_DIG_STORAGE:-${PROJECT_ROOT}/data/storage}"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

print_header() {
    echo -e "${GREEN}=== ${PROJECT_NAME} Test Runner ===${NC}"
    echo "Project root: ${PROJECT_ROOT}"
    echo "Environment: ${GOFR_DIG_ENV}"
    echo "MCP Port (test): ${GOFR_DIG_MCP_PORT}"
    echo "MCPO Port (test): ${GOFR_DIG_MCPO_PORT}"
    echo "Web Port (test): ${GOFR_DIG_WEB_PORT}"
    echo ""
}

start_services() {
    echo -e "${GREEN}=== Starting Ephemeral Docker Services ===${NC}"
    if [ ! -x "${START_DEV_SCRIPT}" ]; then
        echo -e "${RED}start-dev.sh not found or not executable: ${START_DEV_SCRIPT}${NC}"
        exit 1
    fi
    "${START_DEV_SCRIPT}"
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
    # Empty token store
    echo "{}" > "${GOFR_DIG_TOKEN_STORE}" 2>/dev/null || true
    echo -e "${GREEN}Cleanup complete${NC}"
}

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

START_SERVERS=true
COVERAGE=false
COVERAGE_HTML=false
RUN_UNIT=false
RUN_INTEGRATION=false
RUN_ALL=false
STOP_ONLY=false
CLEANUP_ONLY=false
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
        --unit)
            RUN_UNIT=true
            START_SERVERS=false
            shift
            ;;
        --integration)
            RUN_INTEGRATION=true
            START_SERVERS=true
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
            echo "  --unit           Run unit tests only (no servers)"
            echo "  --integration    Run integration tests only (with servers)"
            echo "  --all            Run all test categories"
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

# Initialize token store
if [ ! -f "${GOFR_DIG_TOKEN_STORE}" ]; then
    echo "{}" > "${GOFR_DIG_TOKEN_STORE}"
fi

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

if [ "$RUN_UNIT" = true ]; then
    echo -e "${BLUE}Running unit tests only (no servers)...${NC}"
    uv run python -m pytest ${TEST_DIR}/ -v ${COVERAGE_ARGS} -k "not integration"
    TEST_EXIT_CODE=$?

elif [ "$RUN_INTEGRATION" = true ]; then
    echo -e "${BLUE}Running integration tests (with servers)...${NC}"
    uv run python -m pytest ${TEST_DIR}/integration/ -v ${COVERAGE_ARGS}
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

# Clean up token store
echo -e "${YELLOW}Cleaning up token store...${NC}"
echo "{}" > "${GOFR_DIG_TOKEN_STORE}" 2>/dev/null || true

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
