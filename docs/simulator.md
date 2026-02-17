# Simulator

The **gofr-dig simulator** is a load-testing and integration-testing harness that exercises the full MCP scraping pipeline. It supports three execution modes, mixed-persona workloads, automatic retry/back-off for 429 and transient errors, and produces detailed latency/error reports.

---

## Quick Start

```bash
# Fixture mode — no network, CI-safe
uv run python simulator/run.py \
    --mode fixture --consumers 4 --rate 2.0 --total-requests 20

# Live mode — hit real sites (manual/nightly)
uv run python simulator/run.py \
    --mode live --consumers 2 --rate 0.5 --duration 30s \
    --target-url http://example.com

# MCP mode — drive gofr-dig's MCP tool chain
uv run python simulator/run.py \
    --mode live --consumers 2 --rate 1.0 --duration 60s \
    --mcp-url http://gofr-dig-mcp:8070/mcp

# Record mode — capture and obfuscate live content for fixtures
uv run python simulator/run.py --mode record
```

---

## Modes

| Mode | What it does | Network needed? |
|------|-------------|-----------------|
| `fixture` | Serves pre-recorded HTML from `test/fixtures/html/` via a local fixture server. | No |
| `live` | Fetches real URLs from `sites.json` (or `--target-url`). | Yes |
| `record` | Fetches live URLs, obfuscates PII/text/media, saves to `simulator/fixtures/data/`. | Yes |

---

## CLI Reference

```
uv run python simulator/run.py [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--scenario` | `load` | Scenario preset: `load` or `auth-groups`. |
| `--mode` | `live` | Execution mode: `live`, `fixture`, or `record`. |
| `--consumers` | (varies) | Number of concurrent consumers. |
| `--rate` | `1.0` | Per-consumer request rate (req/s). |
| `--total-requests` | — | Hard cap on total requests (optional). |
| `--duration` | — | Time-based stop (e.g. `30s`, `5m`). |
| `--mcp-url` | `$GOFR_DIG_MCP_URL` | MCP endpoint. When set, consumers call MCP tools instead of direct HTTP. |
| `--mix-file` | — | Path to a consumer mix JSON (see below). |
| `--token-source` | `auto` | Token resolution strategy: `auto`, `mint`, or `env`. |
| `--sites-file` | `simulator/sites.json` | URL list file. |
| `--fixtures-dir` | `test/fixtures/html/` | HTML fixtures directory (for `fixture` mode). |
| `--target-url` | — | Single URL override (ignores sites.json). |
| `--timeout-seconds` | `30.0` | Per-request HTTP timeout. |
| `--output` | — | Path to write JSON report. |
| `--record-output-dir` | `simulator/fixtures/data/` | Where `record` mode saves fixtures. |

At least one of `--total-requests` or `--duration` is required (except for `record` mode).

---

## Consumer Mix File

A mix file lets you define multiple persona groups with different auth tokens. Example (`simulator/mix.example.json`):

```json
{
  "groups": {
    "apac":     { "count": 3, "token": "token_apac" },
    "emea":     { "count": 3, "token": "token_emea" },
    "us":       { "count": 3, "token": "token_us" },
    "multi":    { "count": 1, "token": "token_multi" },
    "public":   { "count": 1, "token": null },
    "attacker": { "count": 1, "token": "token_invalid" }
  }
}
```

Symbolic tokens (`token_apac`, `token_emea`, etc.) are resolved via `--token-source`:

- `env` — reads `GOFR_DIG_SIM_TOKEN_APAC`, etc. from environment.
- `mint` — mints fresh JWTs via Vault `TokenFactory`.
- `auto` — tries env first, falls back to mint.

---

## Rate Limiting & Retry

The simulator transparently retries requests that return HTTP 429, 502, 503, or 504:

- **Exponential back-off** with configurable base (1s) and cap (30s).
- **Retry-After header** is honoured when present and capped at the maximum back-off.
- **Max retries**: 3 per request (configurable via `ConsumerConfig.max_retries`).
- Retries are logged at info level (`sim.consumer_retry`) with attempt count and delay.

Non-retryable errors (4xx other than 429, network failures) are recorded immediately without retry.

---

## Error Analysis

Every failed request is classified into a canonical `error_type`:

| Category | error_type | Trigger |
|----------|-----------|---------|
| Auth | `auth_unauthorized` | HTTP 401 |
| Auth | `auth_forbidden` | HTTP 403 |
| Client | `not_found` | HTTP 404 |
| Client | `rate_limited` | HTTP 429 (after exhausting retries) |
| Client | `client_error` | Other 4xx |
| Server | `server_error` | 5xx (after exhausting retries) |
| Network | `network_timeout` | `httpx.TimeoutException` |
| Network | `network_connect` | `httpx.ConnectError` |
| Network | `network_protocol` | `httpx.RemoteProtocolError` |
| Network | `network_error` | Other `httpx.HTTPError` |
| MCP | `mcp_tool_failed` | MCP tool returned `success: false` |

The JSON report includes per-tool and per-persona error breakdowns:

```json
{
  "overall": {
    "count": 500,
    "error_count": 12,
    "error_rate_pct": 2.4,
    "error_types": {
      "rate_limited": 5,
      "server_error": 4,
      "network_timeout": 3
    },
    "p50_ms": 120.0,
    "p95_ms": 450.0,
    "p99_ms": 980.0
  },
  "by_tool": { ... },
  "by_tool_persona": { ... }
}
```

---

## Report Output

Pass `--output report.json` to write a JSON report at the end of a run. The report includes:

- **config** — the simulation parameters.
- **result** — request count, error count, duration, throughput (RPS).
- **metrics** — latency percentiles (p50/p95/p99), error breakdowns by type, grouped by tool and persona.

---

## Scenarios

### Load (default)

High-concurrency throughput test against fixture or live targets.

```bash
# Library usage
from simulator.scenarios.load import run_load_scenario
result = await run_load_scenario(consumers=50, rate=10.0, duration_seconds=60)
```

### Auth Groups

Multi-persona scenario exercising cross-group session access. Uses a mix file with tokens from different auth groups.

```bash
uv run python simulator/run.py \
    --scenario auth-groups --mode live \
    --mcp-url http://gofr-dig-mcp:8070/mcp \
    --mix-file simulator/mix.example.json \
    --duration 30s
```

---

## Recording Fixtures

Record mode captures live web content, obfuscates it and stores it as reusable fixtures.

Obfuscation pipeline:
1. **PII scrubbing** — emails and phone numbers replaced with placeholders.
2. **Text scrubbing** — visible text nodes replaced with length-matched Lorem Ipsum.
3. **Media scrubbing** — `<img>` src/srcset replaced with placeholder URLs.

```bash
# Record all sites in sites.json
uv run python simulator/run.py --mode record

# Record to a custom directory
uv run python simulator/run.py --mode record --record-output-dir /tmp/fixtures
```

Recorded fixtures are stored with a `meta.json` manifest and per-site subdirectories.

---

## Testing

```bash
# Run simulator tests only (fast, no Docker services needed)
./scripts/run_tests.sh --simulator

# Run targeted test
./scripts/run_tests.sh -k "test_consumer_retry"

# Full test suite (includes simulator)
./scripts/run_tests.sh
```

---

## Architecture

```
simulator/
├── run.py                  # CLI entry point
├── sites.json              # URL list for live / record mode
├── mix.example.json        # Consumer mix file template
├── api/
│   └── report.py           # JSON report builder
├── core/
│   ├── auth.py             # Token minting (Vault integration)
│   ├── consumer.py         # Consumer with retry/back-off
│   ├── engine.py           # Simulator orchestrator
│   ├── mcp_client.py       # MCP streamable-HTTP wrapper
│   ├── metrics.py          # Latency/error collector
│   ├── mix.py              # Mix file parser
│   ├── models.py           # Data classes (Mode, Config, Result)
│   ├── provider.py         # URL providers (Live, Fixture, Static)
│   └── timeparse.py        # Duration string parser
├── fixtures/
│   ├── html_fixture_server.py  # Local HTTP server for fixtures
│   └── storage.py          # Fixture file I/O and metadata
├── recording/
│   ├── obfuscator.py       # PII/text/media scrubbing
│   └── recorder.py         # Live-capture orchestrator
└── scenarios/
    ├── auth.py             # Auth-groups scenario runner
    └── load.py             # Load scenario config builder
```
