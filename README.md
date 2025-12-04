# gofr-dig

GOFR-DIG MCP Server.

## Quick Start

```bash
# Install dependencies
uv pip install -e .

# Start MCP server
python -m app.main_mcp --port 8030

# Start MCPO proxy (OpenAPI wrapper)
python -m app.main_mcpo --mcp-port 8030 --mcpo-port 8031

# Start web server
python -m app.main_web --port 8032
```

## Project Structure

```
app/
  auth/           # JWT authentication
  errors/         # Error mapping
  exceptions/     # Base exceptions
  logger/         # Pluggable logging
  mcp_server/     # MCP tools (implement here)
  mcpo/           # MCPO wrapper
  config.py       # Configuration
  main_mcp.py     # MCP entry point
  main_mcpo.py    # MCPO entry point
  main_web.py     # Web entry point
  web_server.py   # FastAPI web server
docker/           # Docker configuration
scripts/          # Build/run scripts
test/             # Test infrastructure
```

## Next Steps

1. Read `HANDOVER.md` for implementation guide
2. Implement tools in `app/mcp_server/mcp_server.py`
3. Add tests in `test/mcp/`
4. Run tests: `pytest test/`
