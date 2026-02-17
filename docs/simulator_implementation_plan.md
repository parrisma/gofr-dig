# Simulator Implementation Plan

This document outlines the phased implementation strategy for the `gofr-dig` simulator harness. Each phase is broken down into small, verifiable steps.

## Phase 1: Core Framework Skeleton
**Goal:** Establish the project structure and get a minimal viable simulator running that can execute basic HTTP requests against a target.

1. [x] **Directory Structure:** Create `simulator/`, `simulator/core`, `simulator/recording`, `simulator/scenarios`, `test/simulator`.
2. [x] **Models:** Define core data classes in `simulator/core/models.py`:
    - `Task` (instruction: tool, params)
    - `Persona` (config: group, token_type, rate)
    - `SimulationResult` (stats container)
3. [x] **Site Provider:** Implement `simulator/core/provider.py`.
    - `SiteProvider` class that loads `sites.json`.
    - Initially supports `Live` mode only (returning real URLs).
4. [x] **Consumer (V1):** Implement `simulator/core/consumer.py`.
    - `Consumer` class with `httpx.AsyncClient`.
    - `run()` loop that fetches URLs from provider.
    - No auth yet, just plain HTTP GET.
5. [x] **Engine:** Implement `simulator/core/engine.py`.
    - `Simulator` class that spawns N `Consumer` tasks.
    - Handles graceful shutdown (SIGINT).
6. [x] **Initial CLI:** Create `simulator/run.py`.
    - Integration point using `argparse`.
    - Supports `--consumers` and `--duration`.
7. [x] **Verification:** Run `uv run python simulator/run.py --mode live --consumers 1 --rate 0.2 --total-requests 1 --target-url http://example.com` and verify it makes requests (logs to console).
8. [x] **Fixture Mode:** Add built-in HTML fixture server + fixture URL provider, and exercise MCP tool workflow against fixtures.

## Phase 2: Auth Integration & Personas
**Goal:** Enable authorized requests with different user personas (groups A/B/C, Admin, Public) using the project's Vault infrastructure.

1. [x] **Token Factory:** Create `simulator/core/auth.py`.
    - Integration with `gofr_common.auth.AuthService`.
    - Helper to mint tokens for specific groups (`apac`/`emea`/`us`).
    - Helper to generate invalid/expired tokens.
2. [x] **Token injection (V2):** Resolve persona tokens (env or mint) and pass `auth_token` into MCP tool calls.
    - Token resolution happens in the `Simulator`/engine (via mix config + `TokenFactory` fallback).
    - `Consumer` attaches `auth_token` to each MCP tool call when configured.
3. [x] **Persona Configuration:** Create `simulator/config.json` (or `mix.json`).
    - Define distribution: X% Public, Y% Group A, Z% Admin.
4. [x] **MCP Client Wrapper:** Update `Consumer` to speak MCP.
    - Instead of raw GET, format requests as MCP JSON-RPC (or HTTP tool calls).
    - Implement `call_tool(name, args)` helper.
5. [x] **Verification:** Run simulator with mixed personas against a local `gofr-dig` instance. Verify logs show requests from different groups.

## Phase 2.5: Multi-Group Read Authorization (Server)
**Goal:** Make the “multi token cross-group read” scenario meaningful: writes can remain scoped to the primary group, but reads/lists must allow access if the session group is in *any* group listed in the JWT.

1. [x] **Resolve all groups:** Update MCP auth resolution to keep `primary_group` (first) AND `all_groups` from the token.
2. [x] **Session reads use any-group match:** Update session read/list handlers to authorize if `session.group` is in `all_groups`.
3. [x] **Tests:** Add integration tests proving:
    - `token_multi` can read sessions owned by `apac`, `emea`, and `us`.
    - A single-group token cannot read other-group sessions.
4. [x] **Verification:** Run the auth isolation and cross-group read scenarios via `./scripts/run_tests.sh`.

## Phase 3: Metrics & Reporting
**Goal:** Capture performance data and generate actionable reports.

1. [x] **Metrics Collector:** Implement `simulator/core/metrics.py`.
    - `MetricsCollector` class using `asyncio` queues or thread-safe atomic counters (or simple lists for prototype).
    - Track: Request Count, Error Count, Latency (start/end times).
2. [x] **Instrumentation:** Update `Consumer` to report start/stop/error events to collector.
3. [x] **Report Generator:** Implement `simulator/api/report.py`.
    - Calculate p50, p95, p99 latency.
    - Group stats by Tool and Persona.
4. [x] **JSON Output:** Update `run.py` to write `report.json` at end of run.
5. [x] **Verification:** Run simulator and inspect `report.json` for correctness.

## Phase 4: Fixtures & Obfuscation (The "Recorder")
**Goal:** Create the mechanism to capture real web traffic and sanitize it for secure, offline testing.

1. [x] **Fixture Storage:** Define structure for `simulator/fixtures/` (`meta.json` + raw files).
2. [x] **Obfuscator Engine:** Implement `simulator/recording/obfuscator.py`.
    - `scrub_text(html)`: Replace text nodes with length-matched Lorem Ipsum.
    - `scrub_pii(text)`: Regex-based redaction (Email, Phone).
    - `scrub_media(html)`: Replace `<img>` src with placeholders.
3. [x] **Recorder Consumer:** Create a special `RecorderConsumer` persona.
    - Fetches live sites.
    - Passes response through `Obfuscator`.
    - Saves to disk.
4. [x] **Fixture Provider:** Update `SiteProvider` to support `Fixture` mode.
    - Reads URLs from saved `simulator/fixtures/data`.
    - Serves content via `html_fixture_server` (mock).
5. [x] **CLI Update:** Add `--mode [live|record|fixture]`.
6. [x] **Verification:** Record a site, inspect the file (should be unreadable but valid HTML), then run in `fixture` mode.

## Phase 5: Integration & Scenarios
**Goal:** Wire the simulator into the test suite and implement specific test scenarios.

1. [x] **Test Integration:** Create `test/simulator/test_sim_integration.py`.
    - Test that invokes `Simulator` (fixture mode) as a library.
    - Asserts on `SimulationResult`.
2. [x] **Scenario 1: Load:** Define high-concurrency config in `simulator/scenarios/load.py`.
3. [ ] **Scenario 2: Auth:** Define cross-group access scenario (Group A user requests Group B session).
4. [x] **Scenario 3: Housekeeping:** Define specific test script `test/simulator/test_housekeeping.py`.
    - Uses `Simulator` to generate mass sessions.
    - Polls `housekeeper` status or checks storage size.
5. [x] **Shell Script:** Update `scripts/run_tests.sh` to include simulator tests (optional flag `--simulator`).

## Phase 6: Refinement & Hardening
**Goal:** Polish the tool for production/CI use.

1. [x] **Rate Limiting Handling:** Ensure `Consumer` correctly handles `429` (backoff/retry logic).
2. [x] **Error Analysis:** Enhance reporting to break down errors by type (Network vs Auth vs App).
3. [x] **Documentation:** Update `docs/simulator.md` with usage guide.
4. [x] **Final Review:** Code review of the entire module.
