# GOFR-DIG Logging + Vault Integration — Step-by-Step Implementation Plan

## Scope
This plan operationalizes the requirements in `docs/logging_vault_integration_guide.md` into small, trackable delivery steps.

## Delivery Rules
- Use Python 3.11 conventions in this repo.
- Use structured logging (`StructuredLogger`) with key/value fields.
- Never log secrets (tokens, API keys, passwords, Authorization headers, cookies).
- Run validation via `./scripts/run_tests.sh`.

## Phase 0 — Prep and Baseline
- [ ] Create branch: `feat/logging-vault-hardening`.
- [ ] Capture baseline behavior for startup logs, MCP tool logs, fetcher errors, and web/session errors.
- [ ] Confirm production setting target: `GOFR_DIG_LOG_JSON=true`.
- [ ] Document existing Vault logging-related paths currently in use.

## Phase 1 — Logger Hardening (Quick Win)
### 1.1 Redaction + Safety in shared logger
- [x] Update `lib/gofr-common/src/gofr_common/logger/structured_logger.py` to add key-based redaction patterns:
  - [x] `*token*`
  - [x] `*secret*`
  - [x] `*password*`
  - [x] `*authorization*`
  - [x] `*api_key*`
- [x] Add value-based masking for likely credential formats (JWT-like/bearer/long secret-like values).
- [x] Add truncation limits for oversized field values with truncation marker.
- [x] Ensure sanitization runs on all `extra`/kwargs before emit.

### 1.2 Error contract hardening
- [x] Enforce required fields on warning/error logs representing failures:
  - [x] `event`
  - [x] `operation`
  - [x] `stage`
  - [x] `dependency`
  - [x] `cause_type`
  - [x] `remediation`
- [x] Ensure root-cause logging structure includes:
  - [x] root cause
  - [x] impact
  - [x] remediation

### 1.3 Event taxonomy alignment
- [x] Add stable event names for audit/error/info categories.
- [x] Ensure request-path logs include `request_id` and `session_id` when available.

## Phase 2 — App-Level Logging Corrections
### 2.1 MCP sanitization
- [x] Update `app/mcp_server/mcp_server.py` to remove raw `args=arguments` logging.
- [x] Add allowlisted tool-argument summary fields (example: selector presence, depth, timeout, URL host only).
- [x] Emit `tool_invoked` and `tool_completed` events.

### 2.2 Scraping/fetch root-cause consistency
- [x] Update `app/scraping/fetcher.py` retry/failure logs to include:
  - [x] `event`
  - [x] `operation`
  - [x] `stage=fetch`
  - [x] `dependency=target_site`
  - [x] `cause_type`
  - [x] `impact`
  - [x] `remediation`

### 2.3 Web/session error consistency
- [x] Update `app/web_server/web_server.py` session error logs to include:
  - [x] `root_cause_code`
  - [x] `side_effect`
  - [x] remediation guidance

## Phase 3 — Vault Secret Bootstrap for Logging Sink
### 3.1 Startup secret retrieval
- [x] Update `scripts/start-prod.sh` to read logging sink secrets from Vault (AppRole-authenticated path only).
- [x] Export runtime env vars for process scope only (no disk persistence).
- [x] Expected vars:
  - [x] `GOFR_DIG_SEQ_URL`
  - [x] `GOFR_DIG_SEQ_API_KEY`

### 3.2 Container wiring
- [x] Update `docker/compose.prod.yml` to pass logging env vars into MCP and web services.
- [x] Keep non-secrets in env files; keep secrets runtime-injected.

### 3.3 Startup status event
- [x] Emit `event=logging_sink_initialized` with:
  - [x] `sink=seq`
  - [x] `status=ok|degraded`
  - [x] `reason` when degraded

## Phase 4 — Least-Privilege Vault Policy
- [x] Add dedicated policy in `lib/gofr-common/src/gofr_common/auth/policies.py`:
  - [x] `secret/data/gofr/config/logging/*` (read)
  - [x] `secret/metadata/gofr/config/logging/*` (list/read if required)
- [x] Attach logging policy to service role/AppRole provisioning workflow.
- [ ] Remove dependence on over-broad generic config reads for logging secrets.

## Phase 5 — Resilience and Operations
- [x] Implement sink-down behavior: application still starts with local stdout/file logging.
- [x] Add retry/degraded telemetry for sink delivery failure.
- [x] Add alerts for:
  - [x] Vault secret read failure for logging bootstrap
  - [x] logging sink degraded/failure rate
  - [x] retry storms by `url_host`
  - [x] spikes in `permission_denied` / `auth_token_rejected`
  - [x] SSRF and robots-policy block trend changes

## Phase 6 — Tests and Verification
### 6.1 Unit/integration coverage
- [x] Add tests for logger redaction and truncation behavior.
- [x] Add tests ensuring no raw MCP tool args are logged.
- [x] Add tests ensuring error logs include required root-cause and remediation fields.
- [x] Add integration check asserting no secrets appear in emitted logs.
- [ ] Add integration check for Vault outage graceful degradation behavior.

### 6.2 Full validation
- [x] Run full suite: `./scripts/run_tests.sh`.
- [x] Verify no regressions in auth/scraping/session/web components.

## Phase 7 — Runbook and Dashboards
- [x] Add sink credential rotation runbook (with rollback path).
- [ ] Validate key rotation without app image rebuild.
- [ ] Add/confirm SEQ saved views:
  - [x] Auth & Access Audit
  - [x] Dependency Health
  - [x] Crawler Reliability
  - [x] User-impact Errors
  - [x] Security Controls

## Final Sign-Off Checklist
- [x] `GOFR_DIG_LOG_JSON=true` in production.
- [x] Redaction filter enabled and tested.
- [x] No secrets in logs under integration tests.
- [x] Logging secrets read from Vault AppRole, not root token.
- [x] Dedicated logging policy with least privilege.
- [ ] Sink credential rotation runbook tested.
- [x] Vault outage behavior verified (graceful degradation).
- [ ] SEQ/API key rotation tested without app image rebuild.
- [x] `event` taxonomy enforced for audit/error/info logs.
- [x] All error logs include root-cause + remediation fields.
- [x] `tool_invoked` logs are sanitized (no raw argument dumps).
- [x] `request_id` correlation present on request-path logs.

## Ownership Template (fill in)
- [ ] Engineering owner assigned
- [ ] Security owner assigned
- [ ] SRE/Operations owner assigned
- [ ] Target date set
- [ ] Rollout window approved
