# Logging Sink Rotation Runbook (GOFR-DIG)

## Purpose
Operational runbook for rotating SEQ ingestion credentials and handling degraded logging sink behavior without rebuilding application images.

## Preconditions
- Vault is running and unsealed.
- AppRole credentials exist at `secrets/service_creds/gofr-dig.json`.
- Production stack is managed via `scripts/start-prod.sh`.

## Rotate `seq-api-key` (No Image Rebuild)
1. Write new key to Vault path `secret/gofr/config/logging/seq-api-key` (`value=<new-key>`).
2. Optionally verify value exists using AppRole auth path used by `scripts/start-prod.sh`.
3. Restart services with `./scripts/start-prod.sh` (or `./scripts/start-prod.sh --build` only if image changes are needed).
4. Validate startup summary shows `Logging sink: SEQ configured via Vault AppRole`.
5. Confirm `logging_sink_initialized` event has `status=ok` in service logs.

## Rollback
1. Restore previous key in Vault at the same path.
2. Restart services via `./scripts/start-prod.sh`.
3. Confirm sink status returns to `ok`.

## Degraded-Mode Handling
- If Vault or logging secret read fails, service should still start and continue local stdout/file logging.
- Startup output should indicate degraded mode and reason.
- Recovery action:
  - restore Vault availability and secret path values,
  - restart stack,
  - verify `logging_sink_initialized` `status=ok`.

## Alerting Rules and Thresholds

### Severity definitions
- **P1**: immediate customer or security impact requiring on-call page.
- **P2**: significant reliability or auth degradation requiring rapid response.
- **P3**: early-warning trend requiring daytime triage.

### Production alert matrix
1. **Vault logging secret read failures**
  - Signal: `event=vault_secret_read_failed` and `dependency=vault`
  - Threshold: `count >= 3` in `5m`
  - Severity: **P2**
  - Action: verify Vault health/unseal state, AppRole credentials, and logging secret path values.

2. **Logging sink degraded startup**
  - Signal: `event=logging_sink_initialized` with `status=degraded`
  - Threshold: any occurrence in production startup, or persisted degraded state `> 10m`
  - Severity: **P2** (raise to **P1** if all replicas degraded)
  - Action: restore sink connectivity/credentials, restart service, confirm `status=ok`.

3. **Sink delivery failure rate**
  - Signal: `event=logging_sink_delivery_failed` or `dependency=seq` and `cause_type in {network,auth,timeout}`
  - Threshold: failure ratio `> 5%` over `10m` and total attempts `>= 100`
  - Severity: **P2**
  - Action: validate SEQ availability/API key; inspect outbound network path and retries.

4. **Retry storms by host**
  - Signal: `event=fetch_failed` with retry metadata grouped by `url_host`
  - Threshold: per-host retries `>= 50` in `10m` OR `>= 200` in `1h`
  - Severity: **P2**
  - Action: investigate host health/rate limits; tune crawl profile and backoff.

5. **Auth rejection spike**
  - Signal: `event in {permission_denied, auth_token_rejected}`
  - Threshold: `count >= 30` in `5m` OR `3x` baseline in `15m`
  - Severity: **P2**
  - Action: check token issuer/expiry, group mapping, and potential abuse source IPs.

6. **Security block trend anomaly**
  - Signal: `event in {ssrf_request_blocked, robots_policy_blocked}`
  - Threshold: `count >= 20` in `10m` OR `2x` 7-day rolling baseline
  - Severity: **P3** (raise to **P2** if sustained `> 30m`)
  - Action: inspect request sources and target patterns; confirm policy behavior remains expected.

### Routing and suppression guidance
- Route **P1/P2** to on-call pager and incident channel.
- Route **P3** to ops channel and daily triage queue.
- Suppress duplicate alerts for `15m` after trigger, but keep recovery notifications enabled.
- Auto-resolve when metric remains below threshold for `10m`.

## SEQ Saved Views
- Auth & Access Audit.
- Dependency Health.
- Crawler Reliability.
- User-impact Errors.
- Security Controls.
