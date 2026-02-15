# GOFR-DOC Shared Vault Bootstrap Snippets

Purpose: make gofr-doc bootstrap work with shared Vault secrets across GOFR projects without hardcoding gofr-dig paths.

## 1) Bootstrap lookup function (copy into gofr-doc bootstrap script)

Use this in `scripts/bootstrap_gofr_doc.sh` (or equivalent):

```bash
# Resolve shared secrets paths in a portable order:
# 1) Explicit override env (best for CI/ops)
# 2) Standard shared volume mount path
# 3) Project-local secrets mount
# 4) gofr-common fallback in repo
resolve_secrets_dir() {
  local project_root="$1"

  local candidates=()
  if [[ -n "${GOFR_SHARED_SECRETS_DIR:-}" ]]; then
    candidates+=("${GOFR_SHARED_SECRETS_DIR}")
  fi

  candidates+=(
    "/run/gofr-secrets"
    "${project_root}/secrets"
    "${project_root}/lib/gofr-common/secrets"
  )

  local dir
  for dir in "${candidates[@]}"; do
    if [[ -d "${dir}" ]]; then
      echo "${dir}"
      return 0
    fi
  done

  return 1
}

require_vault_bootstrap_artifacts() {
  local project_root="$1"

  local secrets_dir
  if ! secrets_dir="$(resolve_secrets_dir "${project_root}")"; then
    echo "ERROR: No secrets directory found." >&2
    echo "Cause: shared secrets volume is not mounted and local fallbacks do not exist." >&2
    echo "Recovery: mount gofr-secrets to /run/gofr-secrets (or set GOFR_SHARED_SECRETS_DIR)." >&2
    return 1
  fi

  local root_token_file="${secrets_dir}/vault_root_token"
  local unseal_key_file="${secrets_dir}/vault_unseal_key"

  if [[ ! -f "${root_token_file}" ]]; then
    echo "ERROR: vault_root_token not found." >&2
    echo "Context: looked in ${root_token_file}" >&2
    echo "Recovery: run platform bootstrap/manage_vault bootstrap in one GOFR project first." >&2
    return 1
  fi

  if [[ ! -f "${unseal_key_file}" ]]; then
    echo "ERROR: vault_unseal_key not found." >&2
    echo "Context: looked in ${unseal_key_file}" >&2
    echo "Recovery: ensure shared gofr-secrets volume contains unseal artifacts." >&2
    return 1
  fi

  export GOFR_VAULT_ROOT_TOKEN_FILE="${root_token_file}"
  export GOFR_VAULT_UNSEAL_KEY_FILE="${unseal_key_file}"

  # Optional convenience exports if your script expects in-memory vars:
  export GOFR_VAULT_ROOT_TOKEN="$(cat "${root_token_file}")"
  export GOFR_VAULT_UNSEAL_KEY="$(cat "${unseal_key_file}")"

  return 0
}
```

Then call early in bootstrap:

```bash
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
require_vault_bootstrap_artifacts "${PROJECT_ROOT}" || exit 1
```

## 2) Docker Compose mount snippet for gofr-doc

Add shared secrets volume and mount it to a stable path (`/run/gofr-secrets`):

```yaml
services:
  gofr-doc-dev:
    volumes:
      - gofr-secrets:/run/gofr-secrets:rw
      - ./:/home/gofr/devroot/gofr-doc:rw

  gofr-doc-mcp:
    volumes:
      - gofr-secrets:/run/gofr-secrets:ro

  gofr-doc-web:
    volumes:
      - gofr-secrets:/run/gofr-secrets:ro

volumes:
  gofr-secrets:
    external: true
```

Notes:
- Use `rw` only where bootstrap/provisioning writes are required.
- Use `ro` for runtime services.
- Keep the same volume name (`gofr-secrets`) across projects.

## 3) Optional compatibility copy step (if a script requires local files)

If legacy code requires files under `lib/gofr-common/secrets`, copy from shared mount once at startup:

```bash
mkdir -p /home/gofr/devroot/gofr-doc/lib/gofr-common/secrets
cp -n /run/gofr-secrets/vault_root_token /home/gofr/devroot/gofr-doc/lib/gofr-common/secrets/ || true
cp -n /run/gofr-secrets/vault_unseal_key /home/gofr/devroot/gofr-doc/lib/gofr-common/secrets/ || true
chmod 600 /home/gofr/devroot/gofr-doc/lib/gofr-common/secrets/vault_root_token 2>/dev/null || true
chmod 600 /home/gofr/devroot/gofr-doc/lib/gofr-common/secrets/vault_unseal_key 2>/dev/null || true
```

Prefer lookup-based reads over copy when possible.

## 4) Security guardrails

- Do not paste root token/unseal key in chat or commit them to git.
- Use shared-volume access + AppRole provisioning; runtime should not need root token.
- Restrict root-token usage to bootstrap/admin scripts only.

## 5) Validation checklist

After wiring mounts + lookup:

```bash
# inside gofr-doc workspace
./scripts/bootstrap_gofr_doc.sh
./lib/gofr-common/scripts/auth_manager.sh --docker groups list
./scripts/run_tests.sh
```

Expected:
- bootstrap finds shared secrets without any gofr-dig path assumptions;
- auth manager works via admin role credentials;
- tests pass with no secret-path errors.
