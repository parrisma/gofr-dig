# GitHub Copilot Instructions for gofr-dig

## Key Notes (short)
- Use gofr_common; prefer shared helpers over local duplicates.
- Logging: structured fields, no f-strings.
- Exceptions: use app.exceptions and app.errors.mapper.
- Tests: pytest; prefer fixtures in test/conftest.py.
- Python 3.11, Black/Ruff line length 100.

## Auth (keep)
- Do not use app.auth (deleted). Always use gofr_common.auth.
- resolve_auth_config comes from gofr_common.auth.config and returns (jwt_secret, token_store_path, require_auth).
- Convert token_store_path Path to str where needed.

```python
import os
import sys
from typing import Optional

from fastapi import HTTPException
from mcp.server import Server

from gofr_common.auth import AuthService
from gofr_common.logger import Logger

from app.config import Config
from app.exceptions import ValidationError
```

Python environment is managed with UV .. always "uv run" , "uv add" etc. Do not use "python -m venv" or "pip install" directly.

## Common Patterns

### 1. MCP Tool Pattern

```python
from mcp.types import Tool, TextContent

@mcp.tool()
async def my_tool(
    url: str,
    selector: str | None = None,
) -> list[TextContent]:
    """Tool description for AI agents.
    
    Args:
        url: The URL to process
        selector: Optional CSS selector
    """
    try:
        # Validate inputs
        if not url.startswith(("http://", "https://")):
            raise ValidationError("URL must start with http:// or https://")
        
        # Perform operation
        result = await process_url(url, selector)
        
        # Return TextContent list
        return [TextContent(type="text", text=result)]
        
    except Exception as e:
        # Map to MCP error response
        return error_to_mcp_response(e)
```

### 2. Session Management

```python
from app.session.manager import SessionManager

session_manager = SessionManager(storage_dir=Config.get_storage_dir() / "sessions")

# Create session
session_id = session_manager.create_session(
    content="Large content...",
    metadata={"url": url, "timestamp": time.time()},
)

# Retrieve session info
info = session_manager.get_session_info(session_id)

# Get chunk
chunk = session_manager.get_chunk(session_id, chunk_index=0)
```

### 3. Web Scraping with Anti-detection

```python
from app.scraping.fetcher import Fetcher
from app.scraping.state import ScrapingState

state = ScrapingState()
fetcher = Fetcher(state=state)

# Set anti-detection profile
state.impersonate_browser = "chrome_120"
state.respect_robots_txt = True

# Fetch with retry
response = await fetcher.fetch(
    url="https://example.com",
    max_retries=3,
    timeout=30,
)
```

## Environment Variables

### Required for Production
- `GOFR_DIG_JWT_SECRET`: JWT signing secret (64+ char hex recommended)
- `GOFR_DIG_TOKEN_STORE`: Path to token store JSON file

### Optional
- `GOFR_DIG_MCP_PORT`: MCP server port (default: 8070)
- `GOFR_DIG_WEB_PORT`: Web server port (default: 8072)
- `GOFR_DIG_ENV`: Environment (PROD, TEST, DEV)
- `GOFR_DIG_DATA_DIR`: Data directory root
- `GOFR_DIG_STORAGE_DIR`: Document storage directory

## Docker

### Architecture
- Each server (MCP, MCPO, Web) runs as a **separate compose service** (like gofr-iq).
- No supervisor — compose manages lifecycle, healthchecks, and restarts.
- Ports come from `lib/gofr-common/config/gofr_ports.env` (single source of truth).
- Compose files: `docker/compose.dev.yml` (ephemeral/test) and `docker/compose.prod.yml` (persistent).

### Development
```bash
docker/start-dev.sh                            # Start dev stack (compose services)
docker/build-dev.sh                            # Rebuild dev image
docker compose -f docker/compose.dev.yml up -d # Start test stack (3 services)
```

### Production
```bash
docker/start-prod.sh               # One-command deploy (auto-builds, starts compose stack)
docker/start-prod.sh --no-auth     # Start without JWT auth (testing)
docker/start-prod.sh --build       # Force rebuild
docker/start-prod.sh --down        # Stop stack
docker/stop-prod.sh                # Stop stack (alternative)
```

## Documentation References

- [ARCHITECTURE.md](../docs/ARCHITECTURE.md) - System architecture overview
- [AUTH_REPLACEMENT_PLAN.md](../docs/AUTH_REPLACEMENT_PLAN.md) - Auth migration details
- [SESSION_MANAGEMENT_PROPOSAL.md](../docs/SESSION_MANAGEMENT_PROPOSAL.md) - Session design
- [TOOLS.md](../docs/TOOLS.md) - MCP tool reference

## Anti-patterns to Avoid

❌ **Don't import from deleted modules:**
```python
from app.auth import ...           # DELETED
from app.startup.auth_config import ...  # DELETED
```

❌ **Don't construct paths manually:**
```python
path = "data/storage/file.json"   # BAD - not cross-platform
path = Config.get_storage_dir() / "file.json"  # GOOD - uses pathlib
```

❌ **Don't ignore robots.txt without explicit opt-out:**
```python
# Scraping without checking robots.txt is bad practice
response = await fetcher.fetch(url)  # May violate robots.txt

# Instead, use ScrapingState to control
state.respect_robots_txt = True  # Default, respects robots
# OR explicitly disable for testing
state.respect_robots_txt = False
```

❌ **Don't create AuthService without proper config:**
```python
auth = AuthService(secret_key="weak")  # BAD - weak secret, no store

# Instead, use resolve_auth_config
jwt_secret, token_store, _ = resolve_auth_config(
    env_prefix="GOFR_DIG",
    logger=logger,
    ...
)
auth = AuthService(secret_key=jwt_secret, token_store_path=token_store)
```

## Quick Reference Commands

```bash
# Development
source .venv/bin/activate              # Activate venv
python app/main_mcp.py --no-auth       # Run MCP server (dev mode)
python app/main_web.py --no-auth       # Run web server (dev mode)

# Testing
./scripts/run_tests.sh                 # Full test suite
pytest test/mcp/test_get_content.py -v # Specific test file
pytest -k "auth" -v                    # Tests matching pattern

# Code Quality
ruff check .                           # Linting
black --check .                        # Format check
pyright                                # Type checking

# Token Management
./scripts/token_manager.sh create --group admin --expires 86400
./scripts/token_manager.sh list
./scripts/token_manager.sh verify --token <JWT>
./scripts/token_manager.sh revoke --token <JWT>
# Requires GOFR_DIG_JWT_SECRET in environment (or source auth_env.sh)
```

## Need Help?

1. Check [docs/](../docs/) for architecture and design docs
2. Run tests to see working examples: `pytest test/mcp/ -v`
3. Review [test/conftest.py](../test/conftest.py) for fixture patterns
4. Look at existing MCP tools in [app/mcp_server/mcp_server.py](../app/mcp_server/mcp_server.py)

## Authentication & Permissions (CRITICAL - READ FIRST)

### Secret Locations (all under `secrets/` symlinked to `lib/gofr-common/secrets/`)
- **Vault root token**: `secrets/vault_root_token` (for emergency Vault access)
- **Vault unseal key**: `secrets/vault_unseal_key` (auto-unseals on restart)
- **Bootstrap JWT tokens**: `secrets/bootstrap_tokens.json` (admin_token, public_token - 365-day tokens)
- **AppRole credentials**: `secrets/service_creds/{service}_role_id` and `{service}_secret_id` (auto-mounted to containers)
- **Docker env**: `docker/.env` (generated by scripts, contains NEO4J_PASSWORD, VAULT_TOKEN, etc.)
- **OpenRouter API key (Vault)**: `secret/gofr/config/api-keys/openrouter`

### Getting Credentials (ALWAYS use these methods)

#### 1. JWT Tokens (for MCP/API access)
```bash
# Load Vault token + JWT secret into environment (PREFERRED)
source <(./lib/gofr-common/scripts/auth_env.sh --docker)
# Sets: $VAULT_ADDR, $VAULT_TOKEN, $GOFR_JWT_SECRET

# Or extract admin token manually (bootstrap tokens are plain strings)
export TOKEN=$(jq -r '.admin_token' secrets/bootstrap_tokens.json)
```

#### 2. Neo4j Password (for direct database queries)
```bash
# Method 1: From Vault (SAFEST - no shell escaping issues)
export VAULT_TOKEN=$(cat secrets/vault_root_token)
export NEO4J_PASSWORD=$(docker exec -e VAULT_ADDR=http://gofr-vault:8201 -e VAULT_TOKEN=$VAULT_TOKEN \
  gofr-vault vault kv get -field=value secret/gofr/config/neo4j-password)

# Method 2: From docker/.env (if it exists)
source docker/.env  # Sets NEO4J_PASSWORD

# Method 3: Query inside container (RECOMMENDED - avoids auth issues)
docker exec -e NEO4J_USER=neo4j -e NEO4J_PASSWORD="$NEO4J_PASSWORD" gofr-iq-mcp \
  python3 -c "from neo4j import GraphDatabase; ..."
```

#### 3. Vault Access (for managing secrets)
```bash
export VAULT_TOKEN=$(cat secrets/vault_root_token)
export VAULT_ADDR=http://gofr-vault:8201  # or localhost:8201 if on host
# Then use vault CLI or docker exec
docker exec -e VAULT_ADDR=$VAULT_ADDR -e VAULT_TOKEN=$VAULT_TOKEN \
  gofr-vault vault kv get secret/gofr/config/neo4j-password
```

### Auth Management (use gofr-common scripts)
```bash
source <(./lib/gofr-common/scripts/auth_env.sh --docker)
./lib/gofr-common/scripts/auth_manager.sh --docker groups list
./lib/gofr-common/scripts/auth_manager.sh --docker tokens list
./lib/gofr-common/scripts/auth_manager.sh --docker tokens create --groups GROUP --name NAME
```

### Group/Permission Model (IMPORTANT for client queries)
- **All Client nodes MUST have `IN_GROUP` relationship** to appear in `list_clients` queries
- **Admin token** should have access to all groups via `resolve_permitted_groups(admin_token)`
- **Query filter**: `MATCH (c:Client)-[:IN_GROUP]->(g:Group) WHERE g.guid IN $group_guids`
- **Debug access**: Check groups with `auth_manager.sh --docker groups list`
