# Bootstrap on a New Machine

Use this when you have just pulled `gofr-dig` on another machine and need to initialize everything safely.

## Prerequisites

- Docker Engine is installed and running.
- Docker Compose plugin is available (`docker compose`).
- Git is installed.
- You are in the repository root.

## Fast Path (recommended)

From the project root:

```bash
./scripts/bootstrap_gofr_dig.sh --yes
```

What this does (idempotent):
- Initializes git submodules (`lib/gofr-common`).
- Runs platform bootstrap from `gofr-common`.
- Builds dev/prod images if missing.
- Provisions AppRole credentials if missing.
- Seeds Docker secrets volumes.

## If You Pulled Without Submodules

Run this once before bootstrap if `lib/gofr-common` is empty/incomplete:

```bash
git submodule update --init --recursive
```

Then run:

```bash
./scripts/bootstrap_gofr_dig.sh --yes
```

## Start the Stack

After bootstrap completes:

```bash
./scripts/start-prod.sh
```

## (Optional) Bootstrap SEQ Logging Secrets

If `start-prod.sh` reports SEQ logging secrets missing (degraded logging mode), seed the operator-provided SEQ values into Vault:

```bash
./lib/gofr-common/scripts/bootstrap_seq.sh
```

Then restart the stack so services reload env:

```bash
./scripts/start-prod.sh --down
./scripts/start-prod.sh
```

Optional rebuild on first run if needed:

```bash
./scripts/start-prod.sh --build
```

## Verify Auth Bootstrap Works

Run these from project root:

```bash
./lib/gofr-common/scripts/auth_manager.sh --docker groups list
./lib/gofr-common/scripts/bootstrap_auth.sh --docker --groups-only
```

Expected behavior:
- Commands succeed using `gofr-admin-control` credentials.
- No noisy permission warnings for optional policy/JWT bootstrap writes.

## Run Full Validation

```bash
./scripts/run_tests.sh
```

## Common Issues

1. Docker not reachable
- Symptom: bootstrap fails early on Docker checks.
- Fix: start Docker daemon/Desktop and re-run bootstrap.

2. Submodule missing
- Symptom: missing files under `lib/gofr-common`.
- Fix: `git submodule update --init --recursive`.

3. Missing secrets/role creds
- Symptom: auth wrapper says admin creds file missing.
- Fix: re-run `./scripts/bootstrap_gofr_dig.sh --yes` (or `uv run scripts/setup_approle.py` after loading Vault env).

## One-Liner for Most Cases

```bash
git submodule update --init --recursive && ./scripts/bootstrap_gofr_dig.sh --yes && ./scripts/start-prod.sh
```
