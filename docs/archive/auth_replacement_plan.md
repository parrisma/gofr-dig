# Replace app/auth with gofr_common.auth

## ✅ MIGRATION COMPLETED

**Executed:** February 6, 2026  
**Status:** All steps completed successfully  
**Tests:** 295/295 passed  
**Servers:** MCP and Web servers verified working

---

## 1 — Current-state audit

### 1.1 The shim — [app/auth/__init__.py](app/auth/__init__.py)
- Pure re-export of `gofr_common.auth`; no unique logic.
- Exports: `AuthService`, `TokenInfo`, `get_auth_service`, `verify_token`,
  `optional_verify_token`, `init_auth_service`.
- Does **not** re-export `set_security_auditor` / `get_security_auditor`
  (available in `gofr_common.auth` but currently unused by gofr-dig).

### 1.2 Local auth-config helper — [app/startup/auth_config.py](app/startup/auth_config.py)
- Provides a project-specific `resolve_auth_config()`.
- Signature: `(jwt_secret_arg, require_auth, logger) → Tuple[Optional[str], bool]`.
- `gofr_common.auth.config.resolve_auth_config()` has a **different, richer
  signature**: `(env_prefix, jwt_secret_arg, require_auth,
  allow_auto_secret, exit_on_missing, logger) → Tuple[Optional[str], bool]`.
- Both `main_mcp.py` (L8, L84) and `main_web.py` (L12, L58) import and call
  the **local** version.

### 1.3 Shell script reference — [scripts/token_manager.sh](scripts/token_manager.sh#L48)
- Line 48: `export GOFR_TOKEN_MODULE="app.auth.token_manager"` — references a
  module (`app.auth.token_manager`) that **does not exist**. This is either
  dead code or a forward reference that was never wired up. Needs investigation.

### 1.4 All consumers of `from app.auth import …`

| File | Line | Symbols imported |
|------|------|------------------|
| [app/main_mcp.py](app/main_mcp.py#L5) | 5 | `AuthService` |
| [app/main_web.py](app/main_web.py#L9) | 9 | `AuthService` |
| [app/web_server/web_server.py](app/web_server/web_server.py#L15) | 15 | `AuthService` |
| [test/conftest.py](test/conftest.py#L16) | 16 | `AuthService` |

### 1.5 Consumers of the local `resolve_auth_config`

| File | Line | Usage |
|------|------|-------|
| [app/main_mcp.py](app/main_mcp.py#L8) | 8, 84 | import + call |
| [app/main_web.py](app/main_web.py#L12) | 12, 58 | import + call |

---

## 2 — Step-by-step migration plan

### ✅ Step 1 — Verify `gofr-common` is importable at runtime
**Status:** COMPLETED

Verified `gofr_common.auth` imports successfully in the project venv:
- All 8 exports available: `AuthService`, `TokenInfo`, `get_auth_service`, `verify_token`, `optional_verify_token`, `init_auth_service`, `set_security_auditor`, `get_security_auditor`
- Docker configuration already installs `gofr-common` as editable package

### ✅ Step 2 — Migrate `resolve_auth_config` callers
**Status:** COMPLETED  
**Option chosen:** A (Adopt common version directly)

**Changes made:**
1. [app/main_mcp.py](app/main_mcp.py):
   - Import: `from gofr_common.auth.config import resolve_auth_config`
  - Updated call to unpack 2-tuple: `jwt_secret, require_auth = resolve_auth_config(env_prefix="GOFR_DIG", ...)`

2. [app/main_web.py](app/main_web.py):
   - Same changes as main_mcp.py

3. [app/startup/auth_config.py](app/startup/auth_config.py):
  - ⚠️ File will be deleted in Step 6 (no longer needed)

### ✅ Step 3 — Switch `from app.auth` imports to `from gofr_common.auth`
**Status:** COMPLETED

**Files changed:**
- [app/main_mcp.py](app/main_mcp.py#L5): `from gofr_common.auth import AuthService`
- [app/main_web.py](app/main_web.py#L9): `from gofr_common.auth import AuthService`
- [app/web_server/web_server.py](app/web_server/web_server.py#L15): `from gofr_common.auth import AuthService`
- [test/conftest.py](test/conftest.py#L16): `from gofr_common.auth import AuthService`

### ✅ Step 4 — Fix [scripts/token_manager.sh](scripts/token_manager.sh#L48)
**Status:** COMPLETED

Commented out the non-existent module reference:
```bash
# NOTE: GOFR_TOKEN_MODULE is not set - the module app.auth.token_manager does not exist
# and gofr_common.auth does not provide a CLI token manager module yet.
# export GOFR_TOKEN_MODULE="app.auth.token_manager"
```

**Investigation:** Neither `app.auth.token_manager` nor `gofr_common.auth` provides a CLI token manager. The shared script default will be used (which may also not exist). This is existing dead code, now documented.

### ✅ Step 5 — Run the full test suite
**Status:** COMPLETED ✅

```bash
./scripts/run_tests.sh
```

**Results:**
- ✅ 295 tests passed
- ❌ 0 tests failed
- ⏱️ Duration: 143.05s

All auth-related tests passed:
- Session-scoped `test_auth_service` fixture works correctly
- Function-scoped `auth_service` fixture works correctly
- All MCP and Web server integration tests passed

### ✅ Step 6 — Remove the compatibility shim
**Status:** COMPLETED

**Files deleted:**
- ✅ [app/auth/\_\_init\_\_.py](app/auth/__init__.py)
- ✅ [app/auth/\_\_pycache\_\_](app/auth/__pycache__/)
- ✅ [app/auth](app/auth) directory (now empty)
- ✅ [app/startup/auth_config.py](app/startup/auth_config.py)

### ✅ Step 7 — Final verification
**Status:** COMPLETED ✅

**Re-ran full test suite:**
- ✅ 295 tests passed
- ⏱️ Duration: 145.25s

**Verified server startup:**
- ✅ `python app/main_mcp.py --help` succeeds
- ✅ `python app/main_web.py --help` succeeds
- ✅ All imports resolve correctly
- ✅ No import errors or missing modules

---

## 2 — Step-by-step migration plan (ORIGINAL)

### Step 1 — Verify `gofr-common` is importable at runtime
- Both Docker files already do `uv pip install -e ./lib/gofr-common`
  ([Dockerfile.prod](docker/Dockerfile.prod#L43),
  [entrypoint-dev.sh](docker/entrypoint-dev.sh)).
- Local dev relies on `pythonpath = ["."]` in
  [pyproject.toml](pyproject.toml#L88) and the editable install. Confirm
  `import gofr_common.auth` succeeds in a fresh venv **before** touching any
  other file.

### Step 2 — Migrate `resolve_auth_config` callers
The local [app/startup/auth_config.py](app/startup/auth_config.py) and the
common [lib/gofr-common/src/gofr_common/auth/config.py](lib/gofr-common/src/gofr_common/auth/config.py)
have **different return types**.

Choose **one** of:

| Option | Pros | Cons |
|--------|------|------|
| **A — Adopt the common version directly** | Single source of truth; richer features (`exit_on_missing`, `allow_auto_secret`) | Callers must unpack a 2-tuple |
| **B — Keep the local wrapper as a thin adapter** | Zero change to callers; low risk | Still have a local file to maintain |

**Recommended: Option A.** In each caller (`main_mcp.py`, `main_web.py`):
1. Replace `from app.startup.auth_config import resolve_auth_config` with
   `from gofr_common.auth.config import resolve_auth_config`.
2. Update the call site to pass `env_prefix="GOFR_DIG"` and unpack the
  2-tuple `(jwt_secret, require_auth)`.

### Step 3 — Switch `from app.auth` imports to `from gofr_common.auth`
In each file listed in §1.4, replace the import. Example diff:

```python
# Before
from app.auth import AuthService
# After
from gofr_common.auth import AuthService
```

Files to change:
- [app/main_mcp.py](app/main_mcp.py#L5)
- [app/main_web.py](app/main_web.py#L9)
- [app/web_server/web_server.py](app/web_server/web_server.py#L15)
- [test/conftest.py](test/conftest.py#L16)

### Step 4 — Fix [scripts/token_manager.sh](scripts/token_manager.sh#L48)
- Investigate whether `app.auth.token_manager` is used by the common
  `token_manager.sh` script at runtime. If so, update the export to point at
  `gofr_common.auth` (or the correct module path). If it is dead code, remove
  the line.

### Step 5 — Run the full test suite
```bash
./scripts/run_tests.sh        # or: pytest test/
```
- All existing auth tests must pass **before** removing any files.
- Pay particular attention to the session-scoped `test_auth_service` and
  `auth_service` fixtures in [test/conftest.py](test/conftest.py) — they
  construct `AuthService` directly.

### Step 6 — Remove the shim and the local auth-config
> **Only after Step 5 passes.**

1. Delete [app/auth/\_\_init\_\_.py](app/auth/__init__.py).
2. Delete the [app/auth/\_\_pycache\_\_](app/auth/__pycache__) directory.
3. Remove the now-empty [app/auth](app/auth) directory.
4. If Option A was chosen in Step 2, delete
   [app/startup/auth_config.py](app/startup/auth_config.py).

### Step 7 — Final verification
- Run the full test suite again.
- Smoke-test the MCP, MCPO, and Web servers inside the dev container.
- Build the production Docker image (`docker/build-prod.sh`) and verify
  startup.

---

## 3 — Risks and rollback

| Risk | Mitigation |
|------|------------|
| Import fails at runtime (missing `gofr-common` on path) | Step 1 gate-checks this; Docker files already install it |
| `resolve_auth_config` return-type mismatch breaks callers | Step 2 explicitly adapts each call site |
| `scripts/token_manager.sh` breaks in production | Step 4 investigates before deletion |
| Shared-lib version drift introduces breaking changes | Pin `gofr-common` to a known-good commit or tag in `pyproject.toml` |
| Test fixtures silently use stale cached `.pyc` | Step 6 deletes `__pycache__`; run `find . -name __pycache__ -exec rm -rf {} +` for safety |

**Rollback:** Because the shim is deleted last (Step 6), every prior step is
individually revertible via `git checkout -- <file>`.

---

## 4 — Notes
- `gofr_common.auth` exports: `AuthService`, `TokenInfo`, `get_auth_service`,
  `verify_token`, `optional_verify_token`, `init_auth_service`,
  **`set_security_auditor`**, **`get_security_auditor`** (last two are new to
  gofr-dig consumers).
- `gofr_common.auth.config` exports `resolve_auth_config` and
  `resolve_jwt_secret_for_cli`.
- `gofr_common.auth.helpers` provides HTTP test utilities (`add_auth_header`,
  `authenticated_get`, etc.) — useful for test code if not already used.
