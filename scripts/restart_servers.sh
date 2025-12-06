#!/bin/bash
# Restart all GOFR-DIG servers in correct order: MCP → MCPO → Web
# Usage: ./restart_servers.sh [options]
#
# Options:
#   --env PROD|TEST     Set environment (default: PROD for this script)
#   --host HOST         Set bind host for all servers (default: 0.0.0.0)
#   --mcp-port PORT     Override MCP server port
#   --mcp-host HOST     Override MCP server host
#   --mcpo-port PORT    Override MCPO wrapper port
#   --mcpo-host HOST    Override MCPO wrapper host
#   --web-port PORT     Override Web server port
#   --web-host HOST     Override Web server host
#   --kill-all          Stop all servers and exit

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source centralized configuration (defaults to TEST)
export GOFR_DIG_ENV="${GOFR_DIG_ENV:-PROD}"  # Default to PROD for this script
source "$SCRIPT_DIR/gofr-dig.env"

# Parse command line arguments (these override env vars)
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            export GOFR_DIG_ENV="$2"
            shift 2
            ;;
        --host)
            export GOFR_DIG_HOST="$2"
            shift 2
            ;;
        --mcp-port)
            export GOFR_DIG_MCP_PORT="$2"
            shift 2
            ;;
        --mcp-host)
            export GOFR_DIG_MCP_HOST="$2"
            shift 2
            ;;
        --mcpo-port)
            export GOFR_DIG_MCPO_PORT="$2"
            shift 2
            ;;
        --mcpo-host)
            export GOFR_DIG_MCPO_HOST="$2"
            shift 2
            ;;
        --web-port)
            export GOFR_DIG_WEB_PORT="$2"
            shift 2
            ;;
        --web-host)
            export GOFR_DIG_WEB_HOST="$2"
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

# Unset data-related vars so they get recalculated based on GOFR_DIG_ENV
unset GOFR_DIG_DATA GOFR_DIG_STORAGE

# Re-source after env vars may have changed
source "$SCRIPT_DIR/gofr-dig.env"

# Use variables from gofr-dig.env (now includes hosts)
MCP_PORT="$GOFR_DIG_MCP_PORT"
MCPO_PORT="$GOFR_DIG_MCPO_PORT"
WEB_PORT="$GOFR_DIG_WEB_PORT"
MCP_HOST="$GOFR_DIG_MCP_HOST"
MCPO_HOST="$GOFR_DIG_MCPO_HOST"
WEB_HOST="$GOFR_DIG_WEB_HOST"

echo "======================================================================="
echo "GOFR-DIG Server Restart Script"
echo "Environment: $GOFR_DIG_ENV"
echo "Data Root: $GOFR_DIG_DATA"
echo "Network: $GOFR_DIG_NETWORK"
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
echo "Step 2: Starting MCP server ($MCP_HOST:$MCP_PORT)..."
echo "-----------------------------------------------------------------------"

cd "$GOFR_DIG_ROOT"
nohup uv run python -m app.main_mcp \
    --no-auth \
    --host $MCP_HOST \
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
echo "Step 3: Starting MCPO wrapper ($MCPO_HOST:$MCPO_PORT)..."
echo "-----------------------------------------------------------------------"

nohup uv run python -m app.main_mcpo \
    --no-auth \
    --mcp-port $MCP_PORT \
    --mcpo-port $MCPO_PORT \
    --mcpo-host $MCPO_HOST \
    > "$GOFR_DIG_LOGS/gofr_dig_mcpo.log" 2>&1 &

MCPO_PID=$!
echo "  MCPO wrapper starting (PID: $MCPO_PID)"
echo "  Log: $GOFR_DIG_LOGS/gofr_dig_mcpo.log"

# Wait for MCPO to be ready by calling ping endpoint
echo "  Waiting for MCPO to be ready..."
for i in {1..30}; do
    if curl -s -X POST http://localhost:$MCPO_PORT/ping \
        -H "Content-Type: application/json" \
        -d '{}' 2>&1 | grep -q '"status":"ok"'; then
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
echo "Step 4: Starting Web server ($WEB_HOST:$WEB_PORT)..."
echo "-----------------------------------------------------------------------"

nohup uv run python -m app.main_web \
    --no-auth \
    --host $WEB_HOST \
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
