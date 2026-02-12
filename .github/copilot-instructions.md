# Copilot Instructions for gofr-dig

## Core Rules
- Python 3.11. Line length 100 (Black/Ruff).
- Use UV only: `uv run`, `uv add`. No `pip install`, no `python -m venv`.
- Prefer `gofr_common` helpers (auth, config, storage, logging).
- Logging: structured fields, no f-strings — `logger.info("msg", key=value)`.
- Exceptions: use `app.exceptions` + `app.errors.mapper`.
- Tests: pytest; shared fixtures in `test/conftest.py`.
- Tests should be run via `./scripts/run_tests.sh`.
- Paths: use `Config.get_storage_dir() / "subdir"`, never string paths.
- Dev container: avoid `localhost`/`127.0.0.1` for service URLs; use container service names or the published host ports.

## TESTING
Always use scripts/run_tests.sh to run tests (sets PYTHONPATH, env vars, etc) and modify this script if it does not do what is needed or needs enhancing to manage en set up/teardown. When running tests prefer to run FULL tests with servers

## MCP Tools (current)
`ping`, `set_antidetection`, `get_content`, `get_structure`, `get_session_info`, `get_session_chunk`, `list_sessions`, `get_session_urls`, `get_session`

### MCP Tool Pattern (required)
1. Add `Tool(...)` schema in `handle_list_tools`.
2. Route in `handle_call_tool`.
3. Implement `_handle_*` returning `List[TextContent]` via `_json_text`.
4. Use `_error_response(...)` or `_exception_response(...)` for errors.

## Session Manager API
```python
from app.session.manager import SessionManager
from app.config import Config

manager = SessionManager(Config.get_storage_dir() / "sessions")

session_id = manager.create_session(content=page_data, url="https://...", group="grp", chunk_size=4000)
info = manager.get_session_info(session_id, group="grp")
chunk = manager.get_chunk(session_id, 0, group="grp")
sessions = manager.list_sessions()  # or list_sessions(group="grp")
```

## Auth (must use gofr_common)
```python
from gofr_common.auth import AuthService, GroupRegistry
from gofr_common.auth.backends import create_stores_from_env

token_store, group_store = create_stores_from_env("GOFR_DIG")
groups = GroupRegistry(store=group_store)
auth = AuthService(token_store=token_store, group_registry=groups)
```

## Scraping Basics
```python
from app.scraping import fetch_url
from app.scraping.extractor import ContentExtractor
from app.scraping.state import get_scraping_state

state = get_scraping_state()
state.impersonate_browser = "chrome_120"
state.respect_robots_txt = True

result = await fetch_url(url)
content = ContentExtractor(result.content, result.url).extract(selector="#main")
```

## Docker (prod)
```bash
docker/start-prod.sh         # Start stack
docker/start-prod.sh --build # Rebuild
docker/start-prod.sh --down  # Stop
```

## Anti-Patterns
- Do not import `app.auth` (deleted). Use `gofr_common.auth`.
- Do not use `pip install`.
- Do not ignore robots.txt without explicit opt-out.
- Do not use bare `except: pass`.

## Docs
- [docs/TOOLS.md](../docs/TOOLS.md)
- [docs/SESSION_MANAGEMENT_PROPOSAL.md](../docs/SESSION_MANAGEMENT_PROPOSAL.md)
- [docs/SESSION_REMEDIATION_PLAN.md](../docs/SESSION_REMEDIATION_PLAN.md)
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)

## Logging
- Use the **project logger** (e.g., `StructuredLogger`), **not** `print()` or default logging.
- Logs must be **clear and actionable**, not cryptic.
- All errors must include **cause, references/context**, and **recovery options** where possible.

## Hardening Guidance
- Prefer `ApiError` (src/services/api/errors.ts) for API failures and include service/tool context and recovery hints.
- Avoid generic “Failed to parse/failed to load” messages; surface root cause and next step.
- Centralize parsing and error normalization in the API layer; UI should display actionable error messages.
- For MCP failures, include tool name and suggest recovery (re-auth, check MCP health, retry).