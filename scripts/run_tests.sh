#!/bin/bash
# Test runner script with consistent configuration
# This script:
# - Sets consistent JWT secret for all test components
# - Configures test ports for MCP and web servers
# - Points to test data directories
# - Starts servers if needed for integration tests
# - Runs pytest with proper configuration
#
# Usage:
#   ./scripts/run_tests.sh                          # Run all tests
#   ./scripts/run_tests.sh test/mcp/                # Run specific test directory
#   ./scripts/run_tests.sh test/mcp/test_*.py       # Run with pattern
#   ./scripts/run_tests.sh -k "hello"               # Run tests matching keyword
#   ./scripts/run_tests.sh -v test/mcp/             # Run with verbose output
#   ./scripts/run_tests.sh --no-servers test/unit/  # Run without starting servers
#   ./scripts/run_tests.sh --stop                   # Stop servers only
#   ./scripts/run_tests.sh --cleanup-only           # Clean environment only

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Source centralized configuration
export GOFR_DIG_ENV=TEST
source "$SCRIPT_DIR/gofr-dig.env"

# Test configuration constants
export GOFR_DIG_JWT_SECRET="test-secret-key-for-secure-testing-do-not-use-in-production"

# Use variables from gofr-dig.env
STORAGE_DIR="$GOFR_DIG_STORAGE"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== GOFR-DIG Test Runner ===${NC}"
echo "Project root: ${PROJECT_ROOT}"
echo "Data root: ${GOFR_DIG_DATA}"
echo "JWT Secret: ${GOFR_DIG_JWT_SECRET:0:20}..."
echo "MCP Port: ${GOFR_DIG_MCP_PORT}"
echo "Web Port: ${GOFR_DIG_WEB_PORT}"
echo ""

# Kill any leftover servers from previous test runs
echo -e "${YELLOW}Cleaning up any previous test servers...${NC}"
pkill -9 -f "python.*main_mcp.py" 2>/dev/null || true
pkill -9 -f "python.*main_web.py" 2>/dev/null || true
sleep 1

# Purge sessions and storage from previous test runs
echo -e "${YELLOW}Purging token store and transient data...${NC}"

# Empty token store (create empty JSON object)
echo "{}" > "${GOFR_DIG_TOKEN_STORE}" 2>/dev/null || true
echo "Token store emptied: ${GOFR_DIG_TOKEN_STORE}"

echo -e "${GREEN}Cleanup complete${NC}"
echo ""

# Function to check if port is in use
port_in_use() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        lsof -i :"${port}" >/dev/null 2>&1
    elif command -v ss >/dev/null 2>&1; then
        ss -tuln | grep -q ":${port} "
    elif command -v netstat >/dev/null 2>&1; then
        netstat -tuln | grep -q ":${port} "
    else
        # Fallback: try to connect
        timeout 1 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/${port}" >/dev/null 2>&1
    fi
}

# Function to forcibly free a port
free_port() {
    local port=$1
    if ! port_in_use "$port"; then
        return 0
    fi

    if command -v lsof >/dev/null 2>&1; then
        lsof -ti ":${port}" | xargs -r kill -9 2>/dev/null || true
    elif command -v ss >/dev/null 2>&1; then
        ss -lptn "sport = :${port}" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d'=' -f2 | xargs -r kill -9 2>/dev/null || true
    elif command -v netstat >/dev/null 2>&1; then
        netstat -tlnp 2>/dev/null | grep ":${port} " | awk '{print $7}' | cut -d'/' -f1 | xargs -r kill -9 2>/dev/null || true
    fi
    sleep 1
}

# Function to stop all test servers with verification
stop_servers() {
    echo "Killing server processes..."
    pkill -9 -f "python.*main_mcp.py" 2>/dev/null || true
    pkill -9 -f "python.*main_web.py" 2>/dev/null || true
    
    # Also kill by module invocation pattern
    pkill -9 -f "python.*-m.*app.main_mcp" 2>/dev/null || true
    pkill -9 -f "python.*-m.*app.main_web" 2>/dev/null || true
    
    # Wait for processes to die
    sleep 2
    
    # Verify all dead
    if ps aux | grep -E "python.*(main_mcp|main_web)" | grep -v grep >/dev/null 2>&1; then
        echo -e "${RED}WARNING: Some server processes still running after kill attempt${NC}"
        ps aux | grep -E "python.*(main_mcp|main_web)" | grep -v grep
        return 1
    else
        echo "All server processes confirmed dead"
        return 0
    fi
}

# Function to start MCP server for integration tests
start_mcp_server() {
    local log_file="/tmp/mcp_server_test.log"
    echo -e "${YELLOW}Starting MCP server on port ${GOFR_DIG_MCP_PORT}...${NC}"
    
    # Remove old test log if exists
    rm -f "${log_file}"
    
    free_port "${GOFR_DIG_MCP_PORT}"
    
    nohup uv run python app/main_mcp.py \
        --port="${GOFR_DIG_MCP_PORT}" \
        --jwt-secret="${GOFR_DIG_JWT_SECRET}" \
        --token-store="${GOFR_DIG_TOKEN_STORE}" \
        --no-auth \
        --web-url="http://localhost:${GOFR_DIG_WEB_PORT}" \
        > "${log_file}" 2>&1 &
    
    MCP_PID=$!
    echo "MCP Server PID: ${MCP_PID}"
    
    # Wait for server to be ready
    echo -n "Waiting for MCP server to start"
    for i in {1..30}; do
        if ! kill -0 ${MCP_PID} 2>/dev/null; then
            echo -e " ${RED}✗${NC}"
            echo -e "${RED}Process died during startup${NC}"
            tail -20 "${log_file}"
            return 1
        fi
        if port_in_use "${GOFR_DIG_MCP_PORT}"; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 0.5
    done
    
    echo -e " ${RED}✗${NC}"
    echo -e "${RED}Failed to start MCP server${NC}"
    echo "Last 20 lines of server log:"
    tail -20 "${log_file}"
    return 1
}

# Function to start web server for integration tests
start_web_server() {
    local log_file="/tmp/web_server_test.log"
    echo -e "${YELLOW}Starting web server on port ${GOFR_DIG_WEB_PORT}...${NC}"
    
    # Remove old test log if exists
    rm -f "${log_file}"
    
    free_port "${GOFR_DIG_WEB_PORT}"
    
    nohup uv run python app/main_web.py \
        --port="${GOFR_DIG_WEB_PORT}" \
        --jwt-secret="${GOFR_DIG_JWT_SECRET}" \
        --token-store="${GOFR_DIG_TOKEN_STORE}" \
        --no-auth \
        > "${log_file}" 2>&1 &
    
    WEB_PID=$!
    echo "Web Server PID: ${WEB_PID}"
    
    # Wait for server to be ready
    echo -n "Waiting for web server to start"
    for i in {1..30}; do
        if ! kill -0 ${WEB_PID} 2>/dev/null; then
            echo -e " ${RED}✗${NC}"
            echo -e "${RED}Process died during startup${NC}"
            tail -20 "${log_file}"
            return 1
        fi
        if port_in_use "${GOFR_DIG_WEB_PORT}"; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 0.5
    done
    
    echo -e " ${RED}✗${NC}"
    echo -e "${RED}Failed to start web server${NC}"
    echo "Last 20 lines of server log:"
    tail -20 "${log_file}"
    return 1
}

# Parse command line arguments
START_SERVERS=true  # Always start servers by default
STOP_ONLY=false
CLEANUP_ONLY=false
PYTEST_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-servers|--start-servers)
            START_SERVERS=true
            shift
            ;;
        --no-servers|--without-servers)
            START_SERVERS=false
            shift
            ;;
        --cleanup-only)
            CLEANUP_ONLY=true
            shift
            ;;
        --stop|--stop-servers)
            STOP_ONLY=true
            shift
            ;;
        *)
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# Handle stop-only mode
if [ "$STOP_ONLY" = true ]; then
    echo -e "${YELLOW}Stopping servers and exiting...${NC}"
    stop_servers
    exit 0
fi

# Handle cleanup-only mode
if [ "$CLEANUP_ONLY" = true ]; then
    echo -e "${YELLOW}Cleaning up environment and exiting...${NC}"
    echo -e "${YELLOW}Cleaning up any previous test servers...${NC}"
    if ! stop_servers; then
        echo -e "${RED}Force killing remaining processes...${NC}"
        ps aux | grep -E "python.*(main_mcp|main_web)" | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null || true
        sleep 1
        stop_servers || true
    fi
    exit 0
fi

# Start servers if requested
MCP_PID=""
WEB_PID=""
if [ "$START_SERVERS" = true ]; then
    echo -e "${GREEN}=== Starting Test Servers ===${NC}"
    start_mcp_server || { stop_servers; exit 1; }
    start_web_server || { stop_servers; exit 1; }
    echo ""
fi

# Run pytest
echo -e "${GREEN}=== Running Tests ===${NC}"
set +e
if [ ${#PYTEST_ARGS[@]} -eq 0 ]; then
    # Default: run all tests
    uv run python -m pytest test/ -v
else
    # Run with custom arguments
    uv run python -m pytest "${PYTEST_ARGS[@]}"
fi
TEST_EXIT_CODE=$?
set -e

# Stop servers if we started them
if [ "$START_SERVERS" = true ]; then
    echo ""
    echo -e "${YELLOW}Stopping test servers...${NC}"
    if ! stop_servers; then
        echo -e "${RED}Force killing remaining processes...${NC}"
        ps aux | grep -E "python.*(main_mcp|main_web)" | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null || true
        sleep 1
    fi
    # Final verification
    if ps aux | grep -E "python.*(main_mcp|main_web)" | grep -v grep >/dev/null 2>&1; then
        echo -e "${RED}WARNING: Some servers still running after cleanup${NC}"
    fi
fi

# Clean up token store after tests
echo -e "${YELLOW}Cleaning up token store...${NC}"
echo "{}" > "${GOFR_DIG_TOKEN_STORE}" 2>/dev/null || true
echo "Token store emptied"

# Report results
echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}=== Tests Passed ===${NC}"
else
    echo -e "${RED}=== Tests Failed (exit code: ${TEST_EXIT_CODE}) ===${NC}"
    echo "Server logs:"
    echo "  MCP: /tmp/mcp_server_test.log"
    echo "  Web: /tmp/web_server_test.log"
fi

exit $TEST_EXIT_CODE
