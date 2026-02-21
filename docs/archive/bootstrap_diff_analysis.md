# Structural Diff: bootstrap_gofr_dig.sh vs bootstrap_gofr_doc.sh

All `gofr-dig` → `gofr-doc` name swaps (image names, container names, log filenames, usage text, path strings) are excluded. Only **behavioral/functional** differences are listed.

---

## 1. New functions in gofr-doc only: `resolve_secrets_dir()` and `require_vault_bootstrap_artifacts()`

**Which script:** gofr-doc only (lines 168–221)

**What it does:**
- `resolve_secrets_dir(project_root)` searches four locations in priority order for `vault_root_token`:
  1. `$GOFR_SHARED_SECRETS_DIR` (env override)
  2. `/run/gofr-secrets` (shared Docker volume)
  3. `${project_root}/secrets`
  4. `${project_root}/lib/gofr-common/secrets`
- `require_vault_bootstrap_artifacts(project_root)` calls the resolver, then validates that both `vault_root_token` and `vault_unseal_key` exist, and exports five environment variables:
  - `GOFR_SECRETS_DIR`
  - `GOFR_VAULT_ROOT_TOKEN_FILE`
  - `GOFR_VAULT_UNSEAL_KEY_FILE`
  - `GOFR_VAULT_ROOT_TOKEN`
  - `GOFR_VAULT_UNSEAL_KEY`

**Assessment:** Intentional architectural improvement. gofr-doc is designed to run as a second GOFR project that discovers Vault secrets from a shared volume rather than owning them. gofr-dig should adopt this if it will coexist with other GOFR projects on the same host.

---

## 2. main() step ordering: "Resolve shared secrets" step added before platform bootstrap

**Which script:** gofr-doc only (line ~560)

**What it does:** gofr-doc calls `require_vault_bootstrap_artifacts "${PROJECT_ROOT}"` as a dedicated step **before** `run_platform_bootstrap`. gofr-dig has no equivalent step.

**Assessment:** Intentional. gofr-doc's `ensure_vault_healthy()` depends on the exported `GOFR_VAULT_ROOT_TOKEN` variable, so this step must run before Vault health checks. gofr-dig's `ensure_vault_healthy()` does its own inline file lookup so it doesn't need this pre-step. However, this means gofr-dig cannot discover secrets from a shared volume or env override — a capability gap.

---

## 3. ensure_vault_healthy() — root token resolution (step 3 internally)

**Which script:** Both, different logic

**gofr-dig (lines 311–322):**
```bash
local root_token_file=""
if [[ -f "${PROJECT_ROOT}/secrets/vault_root_token" ]]; then
  root_token_file="${PROJECT_ROOT}/secrets/vault_root_token"
elif [[ -f "${secrets_dir}/vault_root_token" ]]; then
  root_token_file="${secrets_dir}/vault_root_token"
else
  die "Vault root token not found."
fi
local root_token
root_token="$(cat "$root_token_file")"
```
Searches two hardcoded paths. `secrets_dir` is set to `${PROJECT_ROOT}/lib/gofr-common/secrets`.

**gofr-doc (lines 414–419):**
```bash
local root_token="${GOFR_VAULT_ROOT_TOKEN:-}"
if [[ -z "$root_token" ]]; then
  die "Vault root token not available (GOFR_VAULT_ROOT_TOKEN empty)."
fi
```
Relies entirely on the env var exported by `require_vault_bootstrap_artifacts`.

**Assessment:** Intentional design difference. gofr-doc decouples secrets resolution from vault health checks. gofr-dig's inline lookup is less portable but self-contained. Neither is buggy, but gofr-dig's approach doesn't support the shared-volume or env-override discovery paths.

---

## 4. ensure_vault_healthy() — extra step 7 in gofr-doc: secrets sync to local gofr-common/secrets

**Which script:** gofr-doc only (lines 449–453)

```bash
local local_secrets="${PROJECT_ROOT}/lib/gofr-common/secrets"
mkdir -p "${local_secrets}"
cp -n "${GOFR_VAULT_ROOT_TOKEN_FILE}" "${local_secrets}/vault_root_token" 2>/dev/null || true
cp -n "${GOFR_VAULT_UNSEAL_KEY_FILE}" "${local_secrets}/vault_unseal_key" 2>/dev/null || true
chmod 600 "${local_secrets}/vault_root_token" "${local_secrets}/vault_unseal_key" 2>/dev/null || true
```

**What it does:** Copies Vault bootstrap artifacts (root token + unseal key) into the local `lib/gofr-common/secrets/` directory using `cp -n` (no-clobber), so that downstream scripts that expect files there (e.g., `manage_vault.sh`) can find them.

**Assessment:** Intentional. Needed because gofr-doc may resolve secrets from a shared volume (`/run/gofr-secrets`) but other scripts expect them locally. gofr-dig doesn't need this because it already has them locally (it's the "primary" project). But if gofr-dig ever moves to shared-volume secrets, it would need this too.

---

## 5. ensure_vault_healthy() — `secrets_dir` local variable

**Which script:** gofr-dig only

**What it does:** gofr-dig declares `local secrets_dir="${PROJECT_ROOT}/lib/gofr-common/secrets"` at the top of `ensure_vault_healthy()`. gofr-doc does not declare this variable (it uses exported `GOFR_*` vars instead).

**Assessment:** Structural consequence of difference #3. Not a bug.

---

## 6. ensure_approle_creds() — number of service roles checked

**Which script:** Both, different logic

**gofr-dig (lines 274–290):** Checks for **two** service role credential files:
- `gofr-dig.json`
- `gofr-admin-control.json`

Both in `secrets/service_creds/` and `lib/gofr-common/secrets/service_creds/`. Only proceeds to provisioning if **either pair** is incomplete.

**gofr-doc (lines 333–340):** Checks for only **one** service role:
- `gofr-doc.json`

Uses a simpler `||` check: if either project or common location has it, skip.

**Assessment:** Intentional project-specific difference. gofr-dig requires an additional `gofr-admin-control` AppRole that gofr-doc does not use.

---

## 7. ensure_approle_creds() — provisioning command

**Which script:** Both, different invocation

**gofr-dig (line 297):**
```bash
bash ./scripts/ensure_approle.sh
```
Checks for `ensure_approle.sh` (shell script).

**gofr-doc (line 348):**
```bash
uv run scripts/ensure_approle.py
```
Checks for `ensure_approle.py` (Python script, run via `uv`).

**Assessment:** Likely intentional evolution. gofr-doc was written later and uses the Python version. **Potential inconsistency:** gofr-dig actually has `scripts/ensure_approle.py` in its workspace but the bootstrap calls `ensure_approle.sh`. If `ensure_approle.sh` is a wrapper around the Python script, this is fine; if they diverge, it's a maintenance risk.

---

## 8. seed_secrets_volume() — return code when script is missing

**Which script:** Both, different behavior

**gofr-dig (lines 303–308):**
```bash
warn "Secrets seeding script not found at ${seed_script}."
warn "Fix: run ./scripts/migrate_secrets_to_volume.sh manually if you add it later."
return 1
```
Returns **1** (failure).

**gofr-doc (lines 355–358):**
```bash
warn "Secrets seeding script not found — skipping."
warn "This step is a placeholder. Add scripts/migrate_secrets_to_volume.sh when needed."
return 0
```
Returns **0** (success).

**Assessment:** Bug/inconsistency. In `main()` both scripts call this step with `|| true`, so the return code is swallowed either way. However, gofr-doc's `return 0` is more correct for a "not yet implemented" placeholder step, while gofr-dig's `return 1` would cause issues if the `|| true` were ever removed. gofr-dig should change to `return 0` to match, since the step is optional.

---

## 9. start_dev_container() — script path

**Which script:** Both, different paths

**gofr-dig:** `scripts/run-dev-container.sh`
**gofr-doc:** `docker/run-dev.sh`

**Assessment:** Intentional project-specific difference. The projects organize their scripts differently. gofr-dig keeps dev scripts in `scripts/`, gofr-doc keeps them in `docker/`.

---

## 10. start_prod_stack() — script path

**Which script:** Both, different paths

**gofr-dig:** `docker/start-prod.sh`
**gofr-doc:** `docker/run-prod.sh`

**Assessment:** Same as above — intentional project-specific layout difference. Also note the naming convention differs: gofr-dig uses `start-prod.sh`, gofr-doc uses `run-prod.sh`.

---

## 11. run_tests_in_dev() — help message path

**Which script:** Both, cosmetically different

**gofr-dig:** `"Fix: start it with --start-dev or run ./scripts/run-dev-container.sh first."`
**gofr-doc:** `"Fix: start it with --start-dev or run ./docker/run-dev.sh first."`

**Assessment:** Consistent with difference #9. Not a bug.

---

## 12. main() — final "Next:" message

**Which script:** Both, different paths

**gofr-dig:** `info "Next: ./scripts/run-dev-container.sh or ./docker/start-prod.sh"`
**gofr-doc:** `info "Next: ./docker/run-dev.sh or ./docker/run-prod.sh"`

**Assessment:** Consistent with differences #9 and #10.

---

## Summary Table

| # | Difference | gofr-dig | gofr-doc | Classification |
|---|-----------|----------|----------|---------------|
| 1 | `resolve_secrets_dir()` + `require_vault_bootstrap_artifacts()` | Missing | Present | Intentional (multi-project support) |
| 2 | "Resolve shared secrets" step in main() | Missing | Present (before platform bootstrap) | Intentional (dependency of gofr-doc vault checks) |
| 3 | Root token resolution in `ensure_vault_healthy()` | Inline file lookup (2 paths) | Env var from pre-step | Intentional (architectural split) |
| 4 | Secrets sync to local gofr-common/secrets | Missing | Present (cp -n + chmod 600) | Intentional (shared-volume support) |
| 5 | `secrets_dir` local var in `ensure_vault_healthy()` | Present | Absent | Structural consequence of #3 |
| 6 | AppRole creds: number of roles | 2 (gofr-dig + gofr-admin-control) | 1 (gofr-doc) | Intentional (project-specific) |
| 7 | AppRole provisioning command | `bash ensure_approle.sh` | `uv run ensure_approle.py` | Potential inconsistency — verify |
| 8 | `seed_secrets_volume()` return code when missing | `return 1` | `return 0` | Bug in gofr-dig (should be 0) |
| 9 | Dev container script path | `scripts/run-dev-container.sh` | `docker/run-dev.sh` | Intentional (project layout) |
| 10 | Prod stack script path | `docker/start-prod.sh` | `docker/run-prod.sh` | Intentional (project layout) |
| 11 | Help message paths | `scripts/` paths | `docker/` paths | Consistent with #9/#10 |
| 12 | Final "Next:" paths | `scripts/` paths | `docker/` paths | Consistent with #9/#10 |

## Recommendations for gofr-dig

1. **Adopt `resolve_secrets_dir()` and `require_vault_bootstrap_artifacts()`** if gofr-dig will coexist with gofr-doc on the same host (shared Vault). This enables shared-volume and env-override discovery.
2. **Fix `seed_secrets_volume()` return code** from `return 1` to `return 0` when the script is missing — it's an optional step.
3. **Verify `ensure_approle.sh` vs `ensure_approle.py`** — gofr-dig has both files in its workspace. Determine which is canonical and align the bootstrap to use it.
