# Port Centralisation Guide for GOFR Projects

> **Purpose**: Step-by-step instructions for removing all hardcoded port numbers
> from a GOFR project so that `lib/gofr-common/config/gofr_ports.env` is the
> single source of truth.  Written so any LLM agent can replicate the work.

---

## 1. Understand the Port Scheme

`gofr_ports.env` defines **every** port for **every** GOFR project:

| Variable pattern | Example (gofr-dig) | Meaning |
|---|---|---|
| `GOFR_<PROJ>_MCP_PORT` | `GOFR_DIG_MCP_PORT=8070` | Production MCP server |
| `GOFR_<PROJ>_MCPO_PORT` | `GOFR_DIG_MCPO_PORT=8071` | Production MCPO proxy |
| `GOFR_<PROJ>_WEB_PORT` | `GOFR_DIG_WEB_PORT=8072` | Production web/REST server |
| `GOFR_<PROJ>_MCP_PORT_TEST` | `GOFR_DIG_MCP_PORT_TEST=8170` | Test MCP (prod + 100) |
| `GOFR_<PROJ>_MCPO_PORT_TEST` | `GOFR_DIG_MCPO_PORT_TEST=8171` | Test MCPO |
| `GOFR_<PROJ>_WEB_PORT_TEST` | `GOFR_DIG_WEB_PORT_TEST=8172` | Test web |
| `GOFR_VAULT_PORT` | `8201` | Vault (shared infra) |
| `GOFR_VAULT_PORT_TEST` | `8301` | Vault test instance |

Replace `<PROJ>` with the project's uppercase short name (DIG, DOC, PLOT, NP, IQ, …).

---

## 2. Audit — Find Every Hardcoded Port

Run from the project root, **excluding** the submodule and the env file itself:

```bash
grep -rn --include='*.sh' --include='*.py' --include='*.yml' --include='*.yaml' \
  -E '\b(PORT_NUMBER_1|PORT_NUMBER_2|...)\b' \
  --exclude-dir='.venv' --exclude-dir='.git' --exclude-dir='__pycache__' \
  | grep -v 'lib/gofr-common' \
  | grep -v 'gofr_ports.env' \
  | grep -v 'GETTING_STARTED.md' \
  | grep -v 'tmp/'
```

Replace the regex with the project's actual port numbers (prod, test, vault).
Example for gofr-dig: `\b(8070|8071|8072|8170|8171|8172|8201|8301)\b`

Categorise every match as one of:

| Category | Action |
|---|---|
| **Shell script — fallback default** (`:-8070`) | Remove fallback → use `:?` or bare `${}` |
| **Python — `os.environ.get("…", "8070")`** | Change to `os.environ["…"]` (require) or `os.environ.get("…", "")` |
| **Python — function default** (`port: int = 8070`) | Replace with `int(os.environ.get("…", "0"))` |
| **Dockerfile — `ARG … =8070`** | Remove default → `ARG GOFR_<PROJ>_MCP_PORT` |
| **Compose — `:-http://…:8201`** | Use `${GOFR_VAULT_PORT}` interpolation |
| **Comment mentioning a number** | Rewrite to say "see gofr_ports.env" |
| **Test data / fixture URL** | Build from env var: `f"http://web:{os.environ.get('…')}"` |

---

## 3. Fix Each File Category

### 3.1 Project env file (`scripts/<proj>.env`)

**Before:**
```bash
export GOFR_DIG_MCP_PORT="${GOFR_DIG_MCP_PORT:-8070}"
```

**After:**
```bash
# Source centralised port config
_PORTS_ENV="${GOFR_DIG_ROOT}/lib/gofr-common/config/gofr_ports.env"
if [ -f "${_PORTS_ENV}" ]; then source "${_PORTS_ENV}"; fi
unset _PORTS_ENV

export GOFR_DIG_MCP_PORT="${GOFR_DIG_MCP_PORT:?GOFR_DIG_MCP_PORT not set — source gofr_ports.env}"
```

Key rule: **`:?` makes the var required** — if `gofr_ports.env` wasn't sourced, the script fails fast with a clear message.

### 3.2 Test runner (`scripts/run_tests.sh`)

The test runner typically sources `gofr_ports.env` early. After that, all `_TEST` vars are guaranteed set.

- Remove every `:-NNNN` fallback for port vars
- Use `:?` for all port exports:
  ```bash
  export GOFR_DIG_MCP_PORT_TEST="${GOFR_DIG_MCP_PORT_TEST:?…not set}"
  ```
- In the "apply docker mode" section, replace internal ports like:
  ```bash
  # Before
  _MCP_INTERNAL="${GOFR_DIG_MCP_PORT_INTERNAL:-8070}"
  # After
  _MCP_INTERNAL="${GOFR_DIG_MCP_PORT}"
  ```

### 3.3 Python entry points (`app/main_mcp.py`, `app/main_mcpo.py`, `app/main_web.py`)

**Before:**
```python
default=int(os.environ.get("GOFR_DIG_MCP_PORT", "8070")),
help="Port number to listen on (default: 8070, or GOFR_DIG_MCP_PORT env var)",
```

**After:**
```python
default=int(os.environ["GOFR_DIG_MCP_PORT"]),
help="Port number to listen on (from GOFR_DIG_MCP_PORT env var)",
```

The env var is **always** set by the entrypoint/compose/test-runner.

### 3.4 Python library code (wrapper, config, web_server classes)

For function/constructor parameter defaults, read the env var at module level:

```python
_MCP_PORT = int(os.environ.get("GOFR_DIG_MCP_PORT", "0"))

class MCPOWrapper:
    def __init__(self, mcp_port: int = _MCP_PORT, ...):
```

Using `0` as the sentinel means "not configured" — callers must pass explicitly or ensure the env var is set.

### 3.5 MCP server (`mcp_server.py`)

- Any `os.environ.get("…_PORT", "NNNN")` → remove the fallback
- Tool schema descriptions mentioning port numbers → replace with generic `PORT`
- `main()` default port → read from env:
  ```python
  async def main(host="0.0.0.0", port: int = 0):
      if port == 0:
          port = int(os.environ["GOFR_DIG_MCP_PORT"])
  ```

### 3.6 Vault scripts (`ensure_approle.sh`, `setup_approle.py`)

**Shell:**
```bash
# Source gofr_ports.env at top of script
source "$PROJECT_ROOT/lib/gofr-common/config/gofr_ports.env"
VAULT_PORT="${GOFR_VAULT_PORT:?…not set}"
# Then use:
export GOFR_VAULT_URL="http://${VAULT_CONTAINER}:${VAULT_PORT}"
```

**Python:**
```python
vault_port = os.environ.get("GOFR_VAULT_PORT", "")
default_url = f"http://gofr-vault:{vault_port}" if vault_port else ""
vault_url = os.environ.get("GOFR_VAULT_URL") or default_url
if not vault_url:
    sys.exit("No Vault URL. Set GOFR_VAULT_URL or GOFR_VAULT_PORT.")
```

### 3.7 Test fixtures (`test/conftest.py`)

```python
# Before
os.environ.setdefault("GOFR_DIG_VAULT_URL", "http://localhost:8301")

# After
vault_port = os.environ.get("GOFR_VAULT_PORT_TEST", "")
if vault_port:
    os.environ.setdefault("GOFR_DIG_VAULT_URL", f"http://localhost:{vault_port}")
```

### 3.8 Test files with fixture URLs

For tests that pass a `base_url` as test data (e.g. `"http://web:8072"`),
define a module-level constant:

```python
import os

TEST_WEB_BASE_URL = "http://web:{}".format(
    os.environ.get("GOFR_DIG_WEB_PORT",
                    os.environ.get("GOFR_DIG_WEB_PORT_TEST", ""))
)
```

Then replace every `"http://web:8072"` in test assertions/inputs with `TEST_WEB_BASE_URL`.

### 3.9 Dockerfiles

Docker `ARG` can't source `.env` files at build time, but compose passes them as
build args. Remove the hardcoded default:

```dockerfile
# Before
ARG GOFR_DIG_MCP_PORT=8070
EXPOSE $GOFR_DIG_MCP_PORT

# After
ARG GOFR_DIG_MCP_PORT
EXPOSE ${GOFR_DIG_MCP_PORT:-0}
```

`EXPOSE` is informational only — actual port mapping is done by compose at runtime.

### 3.10 Compose files

Compose files should **already** use `${GOFR_DIG_MCP_PORT}` (set by the
`start-prod.sh` / `start-test-env.sh` wrapper that sources `gofr_ports.env`).

Fix any vault URL defaults:
```yaml
# Before
- GOFR_DIG_VAULT_URL=${GOFR_DIG_VAULT_URL:-http://gofr-vault:8201}
# After
- GOFR_DIG_VAULT_URL=${GOFR_DIG_VAULT_URL:-http://gofr-vault:${GOFR_VAULT_PORT}}
```

### 3.11 Entrypoint scripts (`entrypoint-prod.sh`)

```bash
# Before
export GOFR_DIG_MCP_PORT="${GOFR_DIG_MCP_PORT:-8070}"
# After
export GOFR_DIG_MCP_PORT="${GOFR_DIG_MCP_PORT:?GOFR_DIG_MCP_PORT not set — source gofr_ports.env}"
```

### 3.12 Comments

Any comment that says a literal port number:
```
# gofr-dig uses 8070-8072
```
becomes:
```
# gofr-dig ports — see lib/gofr-common/config/gofr_ports.env
```

---

## 4. Verify

### 4.1 Grep for zero matches

```bash
grep -rn --include='*.sh' --include='*.py' --include='*.yml' --include='*.yaml' \
  -E '\b(PROD_PORT_1|PROD_PORT_2|...|TEST_PORT_1|...)\b' \
  --exclude-dir='.venv' --exclude-dir='.git' --exclude-dir='__pycache__' \
  | grep -v 'lib/gofr-common' | grep -v 'gofr_ports.env'
```

**Target: zero matches.**

### 4.2 Run the test suite

```bash
./scripts/run_tests.sh
```

All tests must pass. The test runner sources `gofr_ports.env` and exports every
`_TEST` variable, so all env lookups will succeed.

---

## 5. Checklist (copy-paste for PRs)

- [ ] `scripts/<proj>.env` — sources `gofr_ports.env`, all port exports use `:?`
- [ ] `scripts/run_tests.sh` — no `:-NNNN` fallbacks for any port var
- [ ] `scripts/ensure_approle.sh` — sources `gofr_ports.env`, vault URL from env
- [ ] `scripts/setup_approle.py` — vault URL from `GOFR_VAULT_PORT` env var
- [ ] `app/main_*.py` — `os.environ["…"]` for port defaults (no fallback)
- [ ] `app/**/*.py` — function/class defaults read from env at module level
- [ ] `test/conftest.py` — vault URL from `GOFR_VAULT_PORT_TEST`
- [ ] `test/**/*.py` — test URLs built from env vars
- [ ] `docker/Dockerfile.*` — ARGs have no hardcoded defaults
- [ ] `docker/entrypoint-*.sh` — port exports use `:?`
- [ ] `docker/compose.*.yml` — vault URL uses `${GOFR_VAULT_PORT}`
- [ ] `docker/start-*.sh` / `docker/run-*.sh` — no literal port numbers
- [ ] Comments — no literal port numbers (say "see gofr_ports.env")
- [ ] `grep` audit returns zero matches
- [ ] All tests pass

---

## 6. Files NOT to Touch

- `lib/gofr-common/**` — this is a git submodule; changes go there via its own repo
- `gofr_ports.env` itself — this **is** the source of truth
- `docs/GETTING_STARTED.md` — may legitimately show example port numbers for illustration
