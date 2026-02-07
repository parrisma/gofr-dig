Implementation plan (Option B: upgrade gofr‑dig to Vault‑backed shared auth):

Update gofr-common in gofr‑dig

Replace the old gofr‑common with the newer version used by gofr‑iq (the one with auth/backends, VaultIdentity, policies, etc.).
Wire gofr‑dig to new auth factory

Add factory.py equivalent to gofr‑iq (or reuse from gofr‑iq).
Update main_mcp.py to create AuthService via new factory and inject into MCP server.
Add Vault policy entry

In gofr‑dig’s gofr‑common auth/policies.py, add gofr-dig-policy using POLICY_GLOBAL_READ + POLICY_GOFR_CONFIG_READ and service‑specific secret/data/services/dig/*.
AppRole provisioning

Extend setup_approle.py in gofr‑dig to include:
gofr-dig: gofr-dig-policy
Generate /secrets/service_creds/gofr-dig.json.
Docker env wiring

Ensure gofr‑dig MCP container has:
GOFR_AUTH_BACKEND=vault
GOFR_VAULT_URL=http://gofr-vault:${GOFR_VAULT_PORT}
GOFR_VAULT_PATH_PREFIX=gofr/auth
GOFR_VAULT_MOUNT_POINT=secret
GOFR_DIG_JWT_SECRET set from Vault at startup
Mount service_creds/gofr-dig.json to /run/secrets/vault_creds.
JWT secret

Load secret/gofr/config/jwt-signing-secret and export as GOFR_DIG_JWT_SECRET.
Secrets dir (dev only)

Point gofr‑dig scripts to shared secrets dir (symlink or GOFR_SECRETS_DIR).
Validation

Use the same admin token (from gofr‑iq bootstrap) to call gofr‑dig MCP.
Confirm group‑based access works and tokens validate.

--

answers & detail
# Answers for gofr-dig Auth Upgrade

## Critical Blockers — Answers

### 1. Where is the newer gofr-common?

**Both projects use the same GitHub repo** (`git@github.com:parrisma/gofr-common.git`) as a git submodule at `lib/gofr-common`. The versions are different:

| Project | Commit | Key difference |
|---------|--------|----------------|
| gofr-iq | `11ab9b9` (latest) | Has `auth/backends/`, Vault support, policies, identity |
| gofr-dig | `a6fccdf` (older) | File-based auth only, no Vault backend |

**Action:** Update gofr-dig's submodule to latest:
```bash
cd /home/gofr/devroot/gofr-dig
git submodule update --remote lib/gofr-common
# Or:
cd lib/gofr-common && git pull origin main
```

The newer gofr-common adds these modules that gofr-dig is missing:
- `auth/backends/` (factory, vault, memory, file stores)
- `auth/identity.py` (VaultIdentity with AppRole)
- `auth/policies.py` (Vault HCL policies)
- `auth/admin.py` (VaultAdmin for provisioning)
- `vault/` (bootstrap utilities)

And these scripts:
- `auth_env.sh`, `auth_manager.sh`, `auth_manager.py`
- `bootstrap_auth.py`, `bootstrap_auth.sh`, `bootstrap_vault.py`

### 2. Vault service — does it exist?

**Yes, Vault is already running** from gofr-iq's stack and is accessible on `gofr-net`:

```
Container: gofr-vault
Network: gofr-net
Address: http://gofr-vault:8201
```

**gofr-dig-mcp is already on gofr-net** (verified). The dev container (`gofr-dig-dev`) is on `gofr-test-net` — you may need to attach it to `gofr-net` for dev/test access to Vault:
```bash
docker network connect gofr-net gofr-dig-dev
```

**gofr-dig does NOT need to spin up its own Vault.** Use the shared one.

### 3. Token format mismatch (`group` vs `groups`)

The bootstrap tokens use **`groups: ["admin"]`** (array format). This is the **newer format** from gofr-iq's gofr-common.

gofr-dig's old AuthService expects `group` (singular string).

**After updating gofr-common**, the new `AuthService` handles `groups` (array) natively. No manual fix needed — the submodule update brings the compatible code.

---

## Clarifications — Answers

### 4. setup_approle.py

This script lives in **gofr-iq** at `scripts/setup_approle.py`, NOT in gofr-common. It provisions AppRole identities for services.

For gofr-dig, you have two options:
1. **Copy and adapt** gofr-iq's `scripts/setup_approle.py` into gofr-dig, adding `"gofr-dig": "gofr-dig-policy"` to the `SERVICES` dict.
2. **Run it from gofr-iq** with gofr-dig entries added (simpler if you have access).

The policy `gofr-dig-policy` must be added to gofr-common's `auth/policies.py` (or gofr-iq's, then push to gofr-common).

### 5. auth_env.sh and auth_manager.sh

These are in **gofr-common** (the newer version). After updating the submodule, they'll be at:
- `lib/gofr-common/scripts/auth_env.sh`
- `lib/gofr-common/scripts/auth_manager.sh`

### 6. Scope of change

**Update gofr-common via submodule**, then wire gofr-dig to use it. Do NOT duplicate/fork the auth code.

---

## Revised Implementation Plan

### Step 0: Update gofr-common submodule
```bash
cd /home/gofr/devroot/gofr-dig/lib/gofr-common
git fetch origin
git checkout main
git pull origin main
cd ../..
git add lib/gofr-common
git commit -m "Update gofr-common to latest (Vault auth backend)"
```

### Step 1: Add gofr-dig policy to gofr-common
In `lib/gofr-common/src/gofr_common/auth/policies.py`, add:
```python
POLICY_DIG_READ = """
path "secret/data/services/dig/*" {
  capabilities = ["read"]
}
path "secret/data/tokens/dig" {
  capabilities = ["read"]
}
""" + POLICY_GLOBAL_READ + POLICY_GOFR_CONFIG_READ

POLICIES = {
    "gofr-mcp-policy": POLICY_MCP_READ,
    "gofr-web-policy": POLICY_WEB_READ,
    "gofr-dig-policy": POLICY_DIG_READ,
}
```

Push this change to gofr-common origin so gofr-iq can pull it too.

### Step 2: Create app/auth/factory.py in gofr-dig
Copy from gofr-iq's `app/auth/factory.py` (or create minimal version):
```python
from gofr_common.auth import AuthService, GroupRegistry, create_stores_from_env

def create_auth_service(secret_key: str, prefix: str = "GOFR") -> AuthService:
    token_store, group_store = create_stores_from_env(prefix=prefix)
    groups = GroupRegistry(store=group_store)
    return AuthService(
        token_store=token_store,
        group_registry=groups,
        secret_key=secret_key,
        env_prefix=prefix,
    )
```

### Step 3: Create/copy scripts/setup_approle.py
Copy from gofr-iq, update SERVICES dict:
```python
SERVICES = {
    "gofr-dig": "gofr-dig-policy",
}
```

### Step 4: Update docker-compose for gofr-dig MCP
Add to gofr-dig-mcp service:
```yaml
environment:
  - GOFR_DIG_JWT_SECRET=${GOFR_DIG_JWT_SECRET}
  - GOFR_AUTH_BACKEND=vault
  - GOFR_VAULT_URL=http://gofr-vault:8201
  - GOFR_VAULT_PATH_PREFIX=gofr/auth
  - GOFR_VAULT_MOUNT_POINT=secret
volumes:
  - ${HOST_PROJECT_ROOT}/lib/gofr-common/secrets/service_creds/gofr-dig.json:/run/secrets/vault_creds:ro
networks:
  - gofr-net
```

### Step 5: Update start script to load JWT from Vault
In gofr-dig's start-prod.sh (or equivalent):
```bash
GOFR_DIG_JWT_SECRET=$(docker exec -e VAULT_ADDR=http://gofr-vault:8201 \
  -e VAULT_TOKEN=$(cat secrets/vault_root_token) \
  gofr-vault vault kv get -field=value secret/gofr/config/jwt-signing-secret)
export GOFR_DIG_JWT_SECRET
```

### Step 6: Secrets directory
Point gofr-dig to shared secrets:
```bash
# From gofr-dig root
ln -sf /home/gofr/devroot/gofr-iq/lib/gofr-common/secrets ./secrets
```

Or set env var in scripts:
```bash
export GOFR_SECRETS_DIR=/home/gofr/devroot/gofr-iq/lib/gofr-common/secrets
```

### Step 7: Run AppRole provisioning
From gofr-dig (after updating gofr-common and adding policy):
```bash
# Install policies first
source <(./lib/gofr-common/scripts/auth_env.sh --docker)
python3 lib/gofr-common/scripts/bootstrap_auth.py --prefix GOFR

# Then provision AppRole
uv run scripts/setup_approle.py
```

### Step 8: Update main_mcp.py to use new auth factory
Replace old `AuthService` instantiation with factory call.

### Step 9: Validation
Use the admin token from gofr-iq's bootstrap:
```bash
TOKEN=$(jq -r '.admin_token' /home/gofr/devroot/gofr-iq/lib/gofr-common/secrets/bootstrap_tokens.json)
curl -H "Authorization: Bearer $TOKEN" http://gofr-dig-mcp:PORT/health
```

---

## Key Facts Summary

| Item | Value |
|------|-------|
| Vault address | `http://gofr-vault:8201` |
| Network | `gofr-net` (gofr-dig-mcp is already on it) |
| JWT secret Vault path | `secret/gofr/config/jwt-signing-secret` |
| Shared auth Vault path | `gofr/auth` (groups + tokens) |
| Bootstrap tokens | Same file works — tokens are identical |
| gofr-common update | `git submodule update --remote lib/gofr-common` |
