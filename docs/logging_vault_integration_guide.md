# GOFR-DIG Logging + Vault Integration Guide (Production Best Practices)

## Purpose

This document defines how GOFR-DIG logging should be integrated with Vault in production, with a focus on:

- keeping secrets out of logs,
- loading logging sink credentials safely from Vault,
- preserving operational reliability,
- enabling secure central logging (including SEQ).

This is written against the current GOFR-DIG setup:

- logging via `gofr_common.logger.StructuredLogger`,
- auth/config access via Vault + AppRole,
- production runtime via `docker/compose.prod.yml` and `scripts/start-prod.sh`.

---

## Executive Summary

**Vault should not be used as a log transport.** Vault should be used to securely provide logging configuration secrets (API keys, sink credentials, cert material), while logs are emitted to stdout/file and shipped to a log backend (e.g., SEQ).

### Recommended target state

1. **Structured JSON logs only in production** (`GOFR_DIG_LOG_JSON=true`).
2. **No secrets in log payloads** (redaction filter in logger layer).
3. **All sink secrets sourced from Vault at startup** using AppRole credentials.
4. **Least-privilege Vault policy** for logging secrets separate from auth token/group data.
5. **Fail-safe behavior**: app starts if sink is down, but emits a clear degraded-mode event.

---

## Current State (Observed)

- `StructuredLogger` exists and supports JSON output via env (`GOFR_DIG_LOG_JSON`).
- Production compose currently mounts service creds and sets Vault-related env vars for auth.
- Vault path access in policy currently includes broad read access to `secret/data/gofr/config/*`.
- SEQ admin password is stored in Vault at:
  - `secret/gofr/config/seq/admin-password`

### Gaps to close

1. No central redaction/sanitization filter in logger pipeline.
2. No dedicated logging config bootstrap from Vault for app runtime.
3. Policy boundaries for logging secrets are broader than needed.
4. No explicit degraded-mode and retry model for sink failures.

---

## Current Logging Review (Support + DevOps Lens)

This section reflects what the code currently emits and what must improve for incident response, auditability, and root-cause analysis.

### What is currently logged well

- Startup/shutdown lifecycle events are present in `main_mcp.py` and `main_web.py`.
- Fetch pipeline logs retries, status codes, and attempt counts in `app/scraping/fetcher.py`.
- Session endpoints log not-found/validation/error paths in `app/web_server/web_server.py`.
- Error mapper provides recovery strategy text for many known failure codes.

### Critical issues to fix immediately

1. **Potential secret leakage in MCP tool call logging**
  - `app/mcp_server/mcp_server.py` currently logs full tool arguments (`logger.info("Tool called", tool=name, args=arguments)`).
  - This can capture `auth_token`, custom headers, and other sensitive inputs.
  - **Action:** replace full `args` logging with allowlisted, redacted summary fields.

2. **Inconsistent root-cause semantics in error logs**
  - Multiple logs use generic messages such as `Unexpected error ...` with `error=str(e)` but without explicit root-cause class, dependency, and operation stage.
  - **Action:** enforce `cause_type`, `operation`, `stage`, and `dependency` fields on all error logs.

3. **No stable event taxonomy**
  - Many messages are free-text and difficult to query consistently in SEQ.
  - **Action:** require an `event` field with controlled vocabulary.

4. **Audit trail is incomplete for security-relevant actions**
  - Important decisions (auth outcome, permission denial, SSRF block, robots block, rate-limit trigger) are not consistently emitted as dedicated audit events.
  - **Action:** add explicit audit events (see event catalog below).

---

## 2) Logger hardening requirements

---

## Best-Practice Architecture

## 1) Secret boundaries (what goes where)

### In Vault

Store only **logging configuration secrets**, for example:

- `secret/gofr/config/logging/seq-url` (if not public/internal DNS)
- `secret/gofr/config/logging/seq-api-key`
- `secret/gofr/config/logging/tls-ca` (if custom CA)
- optional sink-specific auth tokens

### In environment / non-secret config

- log level (`GOFR_DIG_LOG_LEVEL`)
- JSON toggle (`GOFR_DIG_LOG_JSON=true` in prod)
- sink enable/disable flag
- non-sensitive endpoint hostnames if acceptable

### Never log

- JWT secrets, Vault tokens, AppRole `role_id/secret_id`
- API keys / bearer tokens
- raw `Authorization` headers
- cookie/session identifiers
- full scraped private content when not required

---

## 2) Logger hardening requirements

Implement in `gofr_common.logger` so every GOFR service inherits the same controls.

### Required controls

1. **Key-based redaction**
   - redact any field names matching patterns like:
     - `*token*`, `*secret*`, `*password*`, `*authorization*`, `*api_key*`
2. **Value-based redaction**
   - detect likely credentials (JWT-like strings, long hex/base64 secrets) and mask.
3. **Message template discipline**
   - continue using structured kwargs (`logger.info("msg", key=value)`), not interpolated secrets.
4. **Size limits**
   - cap large values (e.g., request/response bodies) and truncate with marker.
5. **PII controls**
   - hash or drop sensitive personal identifiers where not needed operationally.

### Recommended output fields (minimum)

- `timestamp`
- `level`
- `service` (e.g., `gofr-dig-mcp`)
- `component` (scraper/auth/mcp/web)
- `session_id`
- `request_id` (when available)
- `event` (stable event name)
- `error_code` (mapped app code)
- `recovery_hint` (for actionable ops logs)

### Additional required fields for supportability

- `operation` (e.g., `get_content`, `fetch_url`, `get_session_chunk`)
- `stage` (e.g., `auth`, `validate`, `fetch`, `extract`, `persist`, `respond`)
- `dependency` (e.g., `vault`, `target_site`, `storage`, `seq`)
- `cause_type` (exception class / upstream failure type)
- `request_id` or `trace_id` (cross-service correlation)
- `group` (auth scope, when available and safe)
- `url_host` (host only; avoid full URL when sensitive)

### Root-cause logging rule (mandatory)

For any `warning`/`error` that represents failure or degraded behavior:

1. log **root cause** first (what failed),
2. log **impact** second (what user/API behavior changed),
3. log **remediation** third (operator action or retry behavior).

Example pattern:

- `event=fetch_failed`
- `cause_type=TimeoutError`
- `dependency=target_site`
- `impact=request_failed`
- `remediation=retry_with_higher_timeout_or_validate_target_availability`

### Side-effect vs root-cause policy

Do not log only side effects such as “failed to create session” when the real cause is upstream fetch/extraction/auth failure.

Always include both:

- `root_cause_code` (e.g., `TIMEOUT_ERROR`, `AUTH_ERROR`, `SSRF_BLOCKED`)
- `side_effect` (e.g., `session_not_created`)

---

## 2.1) Audit, Error, and Info Event Model (Canonical)

To make app audit and debugging easy in SEQ, standardize events as follows.

### Audit events (security/compliance)

- `auth_token_verified`
- `auth_token_rejected`
- `group_resolved`
- `permission_denied`
- `ssrf_request_blocked`
- `robots_policy_blocked`
- `rate_limit_inbound_exceeded`
- `vault_secret_read`
- `vault_secret_read_failed`
- `vault_secret_rotated`

Required fields:

- `event`, `actor_type` (`user|service|anonymous`), `group`, `operation`, `result`, `reason_code`, `request_id`

### Error events (operational reliability)

- `fetch_failed`
- `extract_failed`
- `session_store_failed`
- `session_retrieval_failed`
- `vault_dependency_failed`
- `logging_sink_degraded`

Required fields:

- `event`, `error_code`, `cause_type`, `operation`, `stage`, `dependency`, `impact`, `remediation`, `request_id`

### Info events (high-value lifecycle)

- `service_starting`
- `service_started`
- `service_stopping`
- `tool_invoked` (sanitized)
- `tool_completed`
- `crawl_completed`
- `session_created`
- `session_chunk_served`

Required fields:

- `event`, `operation`, `duration_ms` (when applicable), `result`, `request_id`

---

## 2.2) Logging Quality Rules (Developer Contract)

### Rule A — Never log raw secrets

Forbidden log fields/values:

- `auth_token`, `Authorization`, `GOFR_*_JWT_SECRET`, Vault tokens, API keys, cookies.

### Rule B — Log summaries, not payload dumps

- Instead of raw tool args, log:
  - `tool`, `selector_present`, `depth`, `session_mode`, `timeout_seconds`, `url_host`.

### Rule C — Every error must include remediation

- For every error event, include `remediation` as one of:
  - actionable operator step,
  - automated retry behavior,
  - user correction hint.

### Rule D — Error-code alignment

- `error_code` in logs must match API/MCP response error code when available.

### Rule E — Correlation first

- All request-path logs should include `request_id` (or generated equivalent) and `session_id` when present.

---

## 3) Vault access model for logging secrets

## AppRole and policy

Create a dedicated policy for logging secrets, for example:

- policy: `gofr-dig-logging-policy`
- allowed paths:
  - `secret/data/gofr/config/logging/*` (read)
  - `secret/metadata/gofr/config/logging/*` (list/read if needed)

Attach this policy to the existing service role, or a separate role if you want stricter separation.

## Why separate policy

- cleaner audit boundaries,
- easier rotation and blast-radius control,
- avoids overloading generic config scope with unrelated secrets.

---

## 4) Startup flow (production)

At startup (`scripts/start-prod.sh` / entrypoint), perform:

1. AppRole auth (already in place via mounted creds + Vault identity logic).
2. Read logging sink secrets from Vault.
3. Export runtime env vars for app process only (not persisted to disk).
4. Start services.
5. Emit one structured startup event:
   - `event=logging_sink_initialized`
   - include `sink=seq`, `status=ok|degraded`, `reason` if degraded.

## Fail behavior

- **Vault unavailable**:
  - app should still start with local stdout/file logging,
  - mark state as degraded and alert.
- **Sink unavailable**:
  - do not block core API startup,
  - retain logs locally and retry asynchronously.

---

## 5) SEQ-specific guidance

For SEQ integration in GOFR-DIG:

1. Keep SEQ admin password lifecycle in Vault (already implemented).
2. Use a separate ingestion API key for app-to-SEQ writes.
3. Store ingestion key in Vault under `secret/gofr/config/logging/seq-api-key`.
4. Send logs over internal network TLS where possible.
5. Do not reuse Vault root token or SEQ admin password for ingestion.

---

## 6) Implementation plan (file-level)

### A) Logger redaction and safety (high priority)

- Update: `lib/gofr-common/src/gofr_common/logger/structured_logger.py`
  - Add redaction helper for keys/values.
  - Apply sanitization before emitting `extra` fields.
  - Add truncation limits for oversized fields.
  - Enforce required error fields (`event`, `operation`, `cause_type`, `remediation`) in wrappers.

- Update: `app/mcp_server/mcp_server.py`
  - Replace `args=arguments` logging with sanitized allowlisted summary.
  - Emit explicit `tool_invoked` and `tool_completed` events.

- Update: `app/scraping/fetcher.py`
  - Add `event` names and root-cause fields to retry/failure logs.
  - Include `dependency=target_site`, `stage=fetch`, and remediation hints.

- Update: `app/web_server/web_server.py`
  - Standardize session errors with `root_cause_code`, `side_effect`, and remediation.

### B) Logging secret bootstrap from Vault

- Update: `scripts/start-prod.sh`
  - Add optional fetch of logging sink secrets from Vault path.
  - Export `GOFR_DIG_SEQ_URL`, `GOFR_DIG_SEQ_API_KEY` to container env (or inject via compose env interpolation).

- Update: `docker/compose.prod.yml`
  - Pass logging env vars to `mcp` and `web` containers.
  - Keep non-secret values in env file, secret values in host-exported runtime env.

### C) Least privilege policy update

- Update: `lib/gofr-common/src/gofr_common/auth/policies.py`
  - Add `gofr-dig-logging-policy` with read-only logging path scope.
  - Attach to service role in AppRole provisioning workflow.

### D) Ops runbook and alerts

- Add health checks/alerts for:
  - Vault auth failures for logging secret reads,
  - sink delivery failures,
  - backlog growth (if buffering enabled).
  - repeated `permission_denied` / `auth_token_rejected` spikes,
  - SSRF and robots-policy block trends,
  - sustained retry storms against the same host.

---

## 6.1) Query-Ready SEQ Dashboards (Recommended)

Create these saved queries/dashboards:

1. **Auth & Access Audit**
  - events: `auth_token_rejected`, `permission_denied`, `group_resolved`
2. **Dependency Health**
  - events: `fetch_failed`, `vault_dependency_failed`, `logging_sink_degraded`
3. **Crawler Reliability**
  - retries, rate-limits, timeout trends by `url_host`
4. **User-impact Errors**
  - grouped by `error_code`, `operation`, `remediation`
5. **Security Controls**
  - `ssrf_request_blocked`, `robots_policy_blocked`, inbound rate-limit hits

---

## 7) Suggested Vault paths

Use these standardized paths:

- `secret/gofr/config/logging/seq-url`
- `secret/gofr/config/logging/seq-api-key`
- `secret/gofr/config/logging/seq-ca-cert` (optional)
- `secret/gofr/config/seq/admin-password` (already used for UI admin)

---

## 8) Security and compliance checklist

Before production sign-off:

- [ ] `GOFR_DIG_LOG_JSON=true` in production.
- [ ] Redaction filter enabled and tested.
- [ ] No secrets in logs under integration tests.
- [ ] Logging secrets read from Vault AppRole, not root token.
- [ ] Dedicated logging policy with least privilege.
- [ ] Sink credential rotation runbook tested.
- [ ] Vault outage behavior verified (graceful degradation).
- [ ] SEQ/API key rotation tested without app image rebuild.
- [ ] `event` taxonomy enforced for audit/error/info logs.
- [ ] All error logs include root-cause + remediation fields.
- [ ] `tool_invoked` logs are sanitized (no raw argument dumps).
- [ ] `request_id` correlation present on all request-path logs.

---

## 9) Example operational flow (recommended)

1. Security team writes/rotates `seq-api-key` in Vault.
2. `start-prod.sh` (or service restart hook) reads key via AppRole.
3. Service starts with structured JSON logging and sanitized fields.
4. Logs are shipped to SEQ using API key.
5. On sink failure, service logs locally and emits `logging_sink_degraded` events.

---

## 10) What to avoid

- Using Vault as a logging datastore.
- Logging Vault tokens, AppRole creds, or decrypted secret payloads.
- Coupling app availability to SEQ availability.
- Over-broad policies like unrestricted `secret/data/gofr/config/*` for all services.

---

## 11) Recommended rollout phases

### Phase 1 (quick win)

- Enable JSON logs in prod.
- Add redaction filter.
- Read SEQ ingestion key from Vault.

### Phase 2

- Introduce dedicated logging policy and role scoping.
- Add degraded-mode telemetry and alerting.

### Phase 3

- Add rotation automation and zero-downtime sink key reload.
- Add compliance tests for secret leakage in logs.

---

## Final recommendation

Treat Vault as **control-plane for logging secrets**, not the logging data plane. Keep logging structured, sanitized, and resilient. For GOFR-DIG specifically, the most impactful immediate changes are:

1. global redaction in `StructuredLogger`,
2. Vault-sourced SEQ ingestion credentials via AppRole,
3. least-privilege logging policy split from broad config read access.
