# Handover: How `run_tests.sh` Should Start Ephemeral Vault + Servers (gofr-* projects)

Date: 2026-02-15

This document describes what `run_tests.sh` must do to reliably run tests that depend on:
- an ephemeral Vault instance (dev mode)
- ephemeral MCP / MCPO / Web services (docker compose)

It is written to help replicate the working approach used in this repository.

## Non-negotiables

1) Always run tests via `./scripts/run_tests.sh` (not `pytest` directly).
2) Use `uv run ...` for Python execution.
3) In the dev container / docker network, do not use `localhost` to reach other containers. Use Docker service/container names.

## Addressing model (the key to avoiding flaky tests)

There are two different “port worlds”:

A) Container-internal ports (what containers listen on)
- MCP listens on the project’s PROD internal port (example dig: 8070)
- MCPO listens on (example dig: 8071)
- Web listens on (example dig: 8072)

B) Host-published ports (what the host can curl)
- Test runner often publishes prod+100 (example dig: 8170/8171/8172)
- These mappings are ONLY relevant if tests talk to services via host networking.

When the test runner is inside a dev container and the services are on the same docker network, integration tests must use:
- Docker hostnames + container-internal (prod) ports

This repo’s run_tests.sh defaults to docker mode and sets:
- GOFR_DIG_MCP_URL=http://gofr-dig-mcp-test:8070/mcp
- GOFR_DIG_MCPO_URL=http://gofr-dig-mcpo-test:8071
- GOFR_DIG_WEB_URL=http://gofr-dig-web-test:8072

## What `run_tests.sh` needs to do (step-by-step)

### Step 1: Basic environment + ports
- Determine PROJECT_ROOT and `cd` there.
- Export `GOFR_<PROJECT>_ENV=TEST`.
- Source `scripts/<project>.env` if it exists.
- Source centralized ports from:
  - `lib/gofr-common/config/gofr_ports.env`

Why:
- ensures ports are single-source-of-truth and consistent across repos.

### Step 2: Set PYTHONPATH so tests can import gofr-common
- If `<root>/lib/gofr-common/src` exists:
  - include it in PYTHONPATH

Why:
- many tests and app code import `gofr_common.*` directly.

### Step 3: Run code quality gate early (fail-fast)
- Run:
  - `uv run python -m pytest test/code_quality/test_code_quality.py -v`
- If it fails, exit without starting servers.

Why:
- avoids wasting time starting containers only to discover pyright/ruff failures.

### Step 4: Start ephemeral Vault test container
Required characteristics:
- Container name: stable (example: `gofr-vault-test`)
- Network: `gofr-test-net` (create if missing)
- Vault runs in dev mode with a known dev token (example: `gofr-dev-root-token`)
- Vault must be reachable from the dev container and from test service containers.

Recommended docker run pattern:
- `docker run -d --name gofr-vault-test --hostname gofr-vault-test --network gofr-test-net ... vault server -dev`

After start:
- wait until `vault status` succeeds
- enable KV v2 at `secret/` inside that Vault (idempotent)

Export to the test environment:
- `GOFR_<PROJECT>_VAULT_URL`:
  - when running inside docker: `http://gofr-vault-test:8200`
  - when running on the host: `http://localhost:<published_test_port>`
- `GOFR_<PROJECT>_VAULT_TOKEN`:
  - the dev root token

Why:
- tests that create Vault-backed AuthService instances depend on these env vars.

### Step 5: Start ephemeral MCP/MCPO/Web servers (if not `--unit`)
- Use the project’s “start test env” script (example dig: `scripts/start-test-env.sh --build`).
- That script should bring up containers with stable hostnames on `gofr-test-net`, e.g.:
  - `<project>-mcp-test`
  - `<project>-mcpo-test`
  - `<project>-web-test`

- Ensure those containers are connected to `gofr-test-net`.

Why:
- integration tests need stable DNS names and direct container-to-container connectivity.

### Step 6: Apply docker-vs-localhost addressing mode
The runner should support both:

A) Docker mode (default; used in devcontainer)
- Service URLs use docker hostnames + internal prod ports
- Fixture server must bind to `0.0.0.0` so other containers can reach it
- Fixture external host should be the dev container’s name on the network (example: `gofr-dig-dev`)

B) Localhost mode (`--no-docker`)
- Service URLs use `localhost` + published test ports
- Fixture server binds to `127.0.0.1`

Why:
- prevents the classic failure mode: tests use `localhost` from inside a container and accidentally talk to itself.

### Step 7: Run pytest with uv
- Default (no args): run full test suite
- `--unit`: unit tests only, do not start MCP/MCPO/Web servers
- `--integration`: integration tests only

Always run via:
- `uv run python -m pytest ...`

### Step 8: Cleanup (must always happen)
On exit:
- stop MCP/MCPO/Web test stack
- stop + remove the Vault test container
- disconnect dev container from `gofr-test-net` if you connected it

Why:
- prevents “port already in use”, stale containers, and flakiness on the next run.

## Verification checklist (how to know it’s correct)

1) Run `./scripts/run_tests.sh --unit`:
- Should start ephemeral Vault (or at least set GOFR_*_VAULT_* env vars) and run unit tests.
- Should NOT require MCP/MCPO/Web containers.

2) Run `./scripts/run_tests.sh`:
- Should start ephemeral Vault.
- Should start MCP/MCPO/Web containers.
- Integration tests should pass.

3) Confirm addressing:
- In docker mode, printed URLs must be docker hostnames (not localhost).

4) Confirm Vault env vars exist for tests:
- GOFR_<PROJECT>_VAULT_URL
- GOFR_<PROJECT>_VAULT_TOKEN

## Common failure modes and fixes

- Symptom: integration tests timeout calling MCP
  - Cause: URLs point at localhost from inside container
  - Fix: docker mode must use `http://<service-name>:<internal-port>`

- Symptom: auth tests fail with “Vault test configuration missing”
  - Cause: GOFR_<PROJECT>_VAULT_URL / TOKEN not exported
  - Fix: export them right after Vault container starts

- Symptom: Vault KV errors
  - Cause: `secret/` engine not enabled
  - Fix: enable KV v2 at `secret/` during Vault startup

- Symptom: fixture server reachable only from dev container
  - Cause: fixture binds to 127.0.0.1 instead of 0.0.0.0
  - Fix: in docker mode, bind 0.0.0.0 and use dev container hostname for external access
