#!/bin/bash
# Restart all GOFR-DIG servers in correct order: MCP → MCPO → Web
# Usage: ./restart_servers.sh [--kill-all] [--env PROD|TEST]
# Default: TEST environment using test/data

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source centralized configuration (defaults to TEST)
export GOFR_DIG_ENV="${GOFR_DIG_ENV:-PROD}"  # Default to PROD for this script
source "$SCRIPT_DIR/gofr-dig.env"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            export GOFR_DIG_ENV="$2"
            shift 2
            ;;
        --kill-all)
            KILL_ALL=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Re-source after GOFR_DIG_ENV may have changed
source "$SCRIPT_DIR/gofr-dig.env"

# Use variables from gofr-dig.env
MCP_PORT="$GOFR_DIG_MCP_PORT"
MCPO_PORT="$GOFR_DIG_MCPO_PORT"
WEB_PORT="$GOFR_DIG_WEB_PORT"

echo "======================================================================="
echo "GOFR-DIG Server Restart Script"
echo "Environment: $GOFR_DIG_ENV"
echo "Data Root: $GOFR_DIG_DATA"
echo "======================================================================="

# Kill existing processes
echo ""
echo "Step 1: Stopping existing servers..."
echo "-----------------------------------------------------------------------"

# Function to kill process and wait for it to die
kill_and_wait() {
    local pattern=$1
    local name=$2
    local pids=$(pgrep -f "$pattern")
    
    if [ -z "$pids" ]; then
        echo "  - No $name running"
        return 0
    fi
    
    echo "  Killing $name (PIDs: $pids)..."
    pkill -9 -f "$pattern"
    
    # Wait for processes to die (max 10 seconds)
    for i in {1..20}; do
        if ! pgrep -f "$pattern" >/dev/null 2>&1; then
            echo "  ✓ $name stopped"
            return 0
        fi
        sleep 0.5
    done
    
    echo "  ⚠ Warning: $name may still be running"
    return 1
}

# Kill servers in reverse order (Web, MCPO, MCP)
kill_and_wait "app.main_web" "Web server"
kill_and_wait "mcpo --port" "MCPO wrapper"
kill_and_wait "app.main_mcpo" "MCPO wrapper process"
kill_and_wait "app.main_mcp" "MCP server"

# Wait for ports to be released
echo ""
echo "Waiting for ports to be released..."
sleep 2

# Check if --kill-all flag is set
if [ "$KILL_ALL" = true ]; then
    echo ""
    echo "Kill-all mode: Exiting without restart"
    echo "======================================================================="
    exit 0
fi

# Start MCP server
echo ""
echo "Step 2: Starting MCP server (port $MCP_PORT)..."
echo "-----------------------------------------------------------------------"

cd "$GOFR_DIG_ROOT"
nohup uv run python -m app.main_mcp \
    --no-auth \
    --host 0.0.0.0 \
    --port $MCP_PORT \
    --web-url "http://localhost:$WEB_PORT" \
    > "$GOFR_DIG_LOGS/gofr_dig_mcp.log" 2>&1 &

MCP_PID=$!
echo "  MCP server starting (PID: $MCP_PID)"
echo "  Log: $GOFR_DIG_LOGS/gofr_dig_mcp.log"

# Wait for MCP to be ready by checking if it responds to requests
echo "  Waiting for MCP to be ready..."
for i in {1..30}; do
    # MCP requires specific headers, just check if port is responding
    if curl -s -X GET http://localhost:$MCP_PORT/mcp/ \
        -H "Accept: application/json, text/event-stream" \
        2>&1 | grep -q "jsonrpc"; then
        echo "  ✓ MCP server ready"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "  ✗ ERROR: MCP server failed to start"
        tail -20 "$GOFR_DIG_LOGS/gofr_dig_mcp.log"
        exit 1
    fi
done

# Start MCPO wrapper
echo ""
echo "Step 3: Starting MCPO wrapper (port $MCPO_PORT)..."
echo "-----------------------------------------------------------------------"

nohup uv run python -m app.main_mcpo \
    --no-auth \
    --mcp-port $MCP_PORT \
    --mcpo-port $MCPO_PORT \
    > "$GOFR_DIG_LOGS/gofr_dig_mcpo.log" 2>&1 &

MCPO_PID=$!
echo "  MCPO wrapper starting (PID: $MCPO_PID)"
echo "  Log: $GOFR_DIG_LOGS/gofr_dig_mcpo.log"

# Wait for MCPO to be ready by calling ping endpoint
echo "  Waiting for MCPO to be ready..."
for i in {1..30}; do
    if curl -s -X POST http://localhost:$MCPO_PORT/ping \
        -H "Content-Type: application/json" \
        -d '{}' 2>&1 | grep -q '"status":"success"'; then
        echo "  ✓ MCPO wrapper ready"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "  ✗ ERROR: MCPO wrapper failed to start"
        tail -20 "$GOFR_DIG_LOGS/gofr_dig_mcpo.log"
        exit 1
    fi
done

# Start Web server
echo ""
echo "Step 4: Starting Web server (port $WEB_PORT)..."
echo "-----------------------------------------------------------------------"

nohup uv run python -m app.main_web \
    --no-auth \
    --host 0.0.0.0 \
    --port $WEB_PORT \
    > "$GOFR_DIG_LOGS/gofr_dig_web.log" 2>&1 &

WEB_PID=$!
echo "  Web server starting (PID: $WEB_PID)"
echo "  Log: $GOFR_DIG_LOGS/gofr_dig_web.log"

# Wait for Web server to be ready by calling ping endpoint
echo "  Waiting for Web server to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:$WEB_PORT/ping 2>&1 | grep -q '"status":"ok"'; then
        echo "  ✓ Web server ready"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "  ✗ ERROR: Web server failed to start"
        tail -20 "$GOFR_DIG_LOGS/gofr_dig_web.log"
        exit 1
    fi
done

# Summary
echo ""
echo "======================================================================="
echo "All servers started successfully!"
echo "======================================================================="
echo ""
echo "Access URLs:"
echo "  MCP Server:    http://localhost:$MCP_PORT/mcp"
echo "  MCPO Proxy:    http://localhost:$MCPO_PORT"
echo "  Web Server:    http://localhost:$WEB_PORT"
echo ""
echo "Process IDs:"
echo "  MCP:   $MCP_PID"
echo "  MCPO:  $MCPO_PID"
echo "  Web:   $WEB_PID"
echo ""
echo "Logs:"
echo "  MCP:   $GOFR_DIG_LOGS/gofr_dig_mcp.log"
echo "  MCPO:  $GOFR_DIG_LOGS/gofr_dig_mcpo.log"
echo "  Web:   $GOFR_DIG_LOGS/gofr_dig_web.log"
echo ""
echo "To stop all servers: $0 --kill-all"
echo "To view logs: tail -f $GOFR_DIG_LOGS/gofr_dig_*.log"
echo "======================================================================="
