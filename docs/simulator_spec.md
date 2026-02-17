# Simulator Harness Specification: `gofr-dig-sim`

## Overview

A configurable simulation harness for `gofr-dig` that mimics the behavior of concurrent consumers making requests against the MCP server.

**Primary Goals:**
1.  **Stress Testing:** Validate system stability, rate limiting, and throughput under load.
2.  **End-to-End Validation:** Exercise the full scraping pipeline (fetch → extract → parse → session storage).
3.  **Auth Boundary Verification:** Ensure token scoping and group isolation are enforced.
4.  **Data Compliance:** Generate copyright-safe, obfuscated test fixtures from real-world sites.

## System Architecture

The simulator (`simulator/`) is a standalone Python application that can be invoked via CLI or imported as a library for integration tests.

### Components

1.  **`Simulator` (Orchestrator)**
    *   Manages the lifecycle of the simulation.
    *   Initializes the `Consumer` pool.
    *   Aggregates metrics and generates the final report.
    *   Handles signal handling (Ctrl+C) for graceful shutdown.

2.  **`Consumer` (Agent)**
    *   Represents a single concurrent user/agent.
    *   Configurable **Persona**:
        *   **Group:** Target auth group (`apac`, `emea`, `us`, or Public).
        *   **Token:** Valid, Invalid, Expired, None.
        *   **Behavior:** Browsing pattern (Structure-first, Content-heavy, Session-intensive).
    *   Maintains its own session state (cookies, MCP session IDs).
    *    executes a loop of **Tasks** (MCP tool calls).

3.  **`SiteProvider` (Data Source)**
    *   **Live Mode:** Feeds URLs from `simulator/sites.json` (real internet).
    *   **Fixture Mode:** Feeds URLs from the local `HTMLFixtureServer` (CI-safe).
    *   Handles URL distribution strategies (Round-robin, Random, Zipf/Popularity).

4.  **`FixtureRecorder` (Compliance)**
    *   Proxy/Interceptor mode to capture live traffic.
    *   **Obfuscation Engine:**
        *   *Body Text:* Replaced with length-matched synthetic text (Lorem Ipsum style structure).
        *   *Headlines:* Synthetic replacement preserving character count.
        *   *PII:* Redaction of names, emails, phone numbers.
        *   *Dates:* Random offset shifting (preserves formats).
        *   *Images:* Replaced with placeholder SVGs.
        *   *Structure:* **Preserved** (DOM hierarchy, Classes, IDs, attributes) to ensure selectors still work.

5.  **`MetricsCollector`**
    *   Tracks:
        *   Latency (p50, p95, p99).
        *   Throughput (Requests/sec).
        *   Error Rates (HTTP codes, MCP error codes).
        *   Rate Limit Hits (429s).
        *   Auth Failures (401/403).
    *   Exports to JSON.

## Configuration & CLI

```bash
uv run simulator/run.py \
  --mode [live|fixture] \
  --consumers 20 \
  --duration 60s \
  --rate 5.0 \
  --output report.json
```

**Consumer Mix Configuration:**
The simulator accepts a mix definition (e.g., `simulator/mix.json`):
```json
{
  "groups": {
        "apac": { "count": 5, "token": "token_apac" },
        "emea": { "count": 5, "token": "token_emea" },
        "us":   { "count": 5, "token": "token_us" },
    "admin":   { "count": 2, "token": "token_admin" },
    "public":  { "count": 2, "token": null },
    "attacker":{ "count": 1, "token": "invalid_token" }
  }
}
```

### Token Model (3 Groups + 4 Tokens)

The simulator will support (at minimum) four token types for the three groups:

1. `token_apac` — access to `apac` only
2. `token_emea` — access to `emea` only
3. `token_us` — access to `us` only
4. `token_multi` — access to all groups (`apac` + `emea` + `us`)

**Clarified semantics:**
- The multi-group token is primarily for **cross-group read** validation.
- It is acceptable if session *writes* (session ownership) remain scoped to the token’s **primary group**.

**Implication for gofr-dig (server-side):**
- Session read/list authorization must support **any-group match** (i.e., a token with groups `apac, emea, us` should be able to read sessions owned by any of those groups).
- This is required for the simulator’s “multi token cross-group read” scenario to be meaningful.

## Test Scenarios

### 1. Load Test (CI/Nightly)
*   **Source:** Local Fixtures.
*   **Scale:** 50 Consumers.
*   **Goal:** Verify no crashes, memory leaks, or 500 errors under sustained load.

### 2. Rate Limit Verification
*   **Source:** Local Fixtures.
*   **Scale:** Single Consumer bursting > configured limit.
*   **Goal:** Verify `RATE_LIMIT_EXCEEDED` error is returned and resets correctly.

### 3. Auth Isolation
*   **Source:** Local Fixtures.
*   **Action:**
    *   Group A consumer creates a session.
    *   Group B consumer attempts `get_session` on A's ID.
*   **Goal:** Verify `PERMISSION_DENIED` or `SESSION_NOT_FOUND`.

### 4. Housekeeping & Storage Limits
*   **Source:** Synthetic Data Generator.
*   **Action:**
    *   Consumers generate sessions rapidly until storage > configured limit (e.g., 100MB).
    *   Verify `housekeeper` service (or mocked invocation) triggers.
    *   Assert that *oldest* sessions are deleted and *newest* remain.
    *   Assert that total storage drops below high-water mark.
*   **Goal:** Verify rotation logic and that the system doesn't crash from disk exhaustion.

### 5. Content Reliability (Manual/Live)
*   **Source:** Real Sites (`sites.json`).
*   **Action:** Fetch top sites.
*   **Goal:** Verify non-empty content, valid JSON, and no `BLOCK` or `CAPTCHA` errors (validating anti-detection).

## Implementation Plan

### Phase 1: Core Harness (`simulator/`)
1.  Implement `SiteProvider` to read `sites.json`.
2.  Implement `Consumer` class with `asyncio` loop.
3.  Implement basic `Simulator` runner.
4.  Add CLI entry point.

### Phase 2: Obfuscation & Recording
1.  Create `FixtureRecorder` class.
2.  Implement `Obfuscator` logic (lorem replacement, DOM preservation).
3.  Add "Record Mode" to CLI to generate fixtures from `sites.json`.

### Phase 3: Integration
1.  Add `test/simulator/test_sim_integration.py` which calls the simulator programmatically.
2.  Wire into `scripts/run_tests.sh`.

## Directory Structure

```
simulator/
├── __init__.py
├── run.py                 # CLI Entry point
├── config.py              # Settings
├── core/
│   ├── engine.py          # Simulator loop
│   ├── consumer.py        # User agent logic
│   ├── metrics.py         # Stats collection
│   └── provider.py        # URL/Site source
├── recording/
│   ├── recorder.py        # Capture logic
│   └── obfuscator.py      # Sanitization logic
├── sites.json             # Live target list
└── fixtures/              # Generated safe test data
    ├── meta.json
    └── data/
        ├── nikkei_asia.html
        └── ...
```
