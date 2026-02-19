# Simulator effectiveness review (gofr-dig)

Date: 2026-02-18

## Executive summary

The simulator is already useful today as a CI-safe harness for exercising HTTP fetch behavior and (optionally) a subset of the MCP tool chain. It has a clear architecture (engine -> consumers -> provider + metrics) and good unit/integration coverage for its core building blocks (fixture mode runs, retry/backoff, metrics aggregation, recorder obfuscation).

However, if the goal is to "verify real world behaviour of gofr-dig", the current simulator is only partially there:

- Fixture mode validates deterministic parsing and basic throughput behavior, but not the live scraping failure modes (WAFs, dynamic pages, redirects, regional variants, timeouts).
- MCP mode currently calls a fixed sequence of tools (get_structure -> get_content -> session reads) and does not model the actual mix of tool usage and error recovery logic expected from real clients.
- Record mode exists and writes obfuscated fixtures, but there is no built-in workflow that turns those recorded fixtures into an immediately runnable fixture-mode suite (the recorder writes to simulator/fixtures/data/, while fixture mode currently uses test/fixtures/html/ by default).

Net: readiness is "good for CI regression and basic integration", "incomplete for real-world behavioral validation".

## What exists today (by capability)

### 1) Core simulation engine (good)

- Orchestration: simulator/core/engine.py
  - Spawns N consumers, shares a request budget, stops on budget exhaustion or duration.
  - Supports fixture server lifecycle in fixture mode.
  - Records metrics and emits a SimulationResult.

- Consumer loop: simulator/core/consumer.py
  - Direct HTTP mode: GET URLs from a provider.
  - Retry/backoff: retries on 429/502/503/504 with exponential backoff and Retry-After support.
  - MCP mode: calls MCP tools via streamable-http client.

- Metrics: simulator/core/metrics.py
  - Reservoir sampling for bounded memory.
  - Reports overall and grouped stats (by tool, by tool+persona) with p50/p95/p99.

### 2) Deterministic CI-safe operation (good)

- Fixture server: simulator/fixtures/html_fixture_server.py
  - Simple HTTP fixture server; addressing supports docker usage via external host.

- Tests validate fixture mode: test/simulator/test_sim_integration.py
  - Confirms the engine completes and the result fields are sane.

### 3) Auth boundary testing (partially good)

- Token minting: simulator/core/auth.py
  - Uses Vault-backed JwtSecretProvider + AuthService to mint tokens.
  - Can create required groups if missing.
  - Also supports env-provided tokens for cases where Vault access is undesired.

- Auth boundary scenario: simulator/scenarios/auth_groups.py
  - Uses MCP tool calls to create sessions under apac/emea/us and validates:
    - multi token can read sessions across groups
    - wrong single-group token gets PERMISSION_DENIED

This is a strong starting point for validating group isolation.

### 4) Real-world fixture capture (partially good)

- Recorder: simulator/recording/recorder.py
  - Fetches URLs and writes one obfuscated index.html per site.

- Obfuscation: simulator/recording/obfuscator.py
  - Scrubs PII (email, phone), visible text, and image src/srcset.
  - Preserves DOM structure and attributes.

What is missing is an end-to-end "record -> run fixture-mode against recorded set" workflow.

## Gaps vs "real-world behavior" and how to make simulator more effective

### Gap A: Not measuring the things that break in real scraping

Real-world scraping failures are often not "HTTP 500". More common issues:

- 200 responses with bot blocks or interstitials
- 403/429 with non-standard headers, JS challenges
- HTML that is not parseable, truncated, or heavily script-generated
- inconsistent content types (text/plain, application/json), gzip issues
- redirects to paywalls or regional pages

Simulator currently:

- classifies failures mostly by HTTP status and httpx exception class.
- does not detect "block pages" (content heuristics).

High-impact next step:

- Add a lightweight "response classification" layer in the consumer:
  - Identify bot-block patterns by heuristics (title contains "Access Denied", common vendor keywords, presence of captcha markers).
  - Record these as canonical error_type values (block_page, captcha, paywall_redirect, etc.).

This improves signal quality for live runs without changing the service.

### Gap B: MCP mode is fixed-sequence and does not reflect realistic tool mixes

Current MCP flow per iteration:

- get_structure
- get_content (session=True)
- get_session_info (if session_id)
- get_session_chunk (chunk 0)

To better mimic real clients:

- Make the MCP "task mix" configurable:
  - per-iteration choose from a weighted set of tasks (get_structure only, get_content only, get_content parse_results true/false, session reads, list_sessions, etc.).
  - tie those weights to the existing mix file concept (persona or group) so different personas can behave differently.

This is the single most impactful change to make the simulator reflect production usage patterns.

### Gap C: Fixture mode uses test fixtures, not recorded fixtures

Today:

- record mode writes to simulator/fixtures/data/
- fixture mode defaults to test/fixtures/html/

This prevents the recorder from being an easy on-ramp.

High-impact next step:

- Add an explicit --fixtures-dir default for fixture mode that points to the recorder output directory, or add a new flag:
  - --recorded-fixtures-dir (default simulator/fixtures/data)
  - and/or a scenario that uses FixtureStore.meta.json to build a URL list.

This enables a workflow like:

- record once (manual)
- run fixture mode repeatedly (CI, local) against the recorded corpus

### Gap D: Live mode is "direct HTTP" by default, but the system under test is the MCP pipeline

If the objective is to validate gofr-dig behavior, MCP mode should be the primary path.

Suggested approach:

- Keep direct HTTP mode as a connectivity/load tool.
- Provide a first-class "mcp-load" scenario preset that requires --mcp-url.

### Gap E: Readiness automation (how to run it) can be tighter

The simulator is runnable as:

- uv run python simulator/run.py ...

But the experience of "start the stack, point simulator at it, mint tokens" is still manual.

Practical next steps to reduce friction:

- Document one canonical command sequence for:
  - starting the docker test/prod stack
  - running fixture-mode load test
  - running auth-groups test

- Provide example env vars for tokens when Vault is not reachable.

## State of readiness

- CI regression harness readiness: HIGH
  - fixture-mode engine + tests are solid.
  - metrics and retry logic are covered.

- Real-world behavior validation readiness: MEDIUM/LOW
  - MCP mode exists but uses a fixed call pattern.
  - live mode currently does not apply MCP pipeline unless --mcp-url is provided.
  - no block-page detection.

- Fixture recording readiness: MEDIUM
  - recorder + obfuscator exist and are tested.
  - missing the integrated workflow to use recorded fixtures in fixture-mode runs.

## Concrete next steps (recommended order)

1. Unify fixture workflow
   - Make it easy to run fixture-mode against simulator/fixtures/data output.
   - Add a small scenario helper to run against recorded meta.json if present.

2. Make MCP tool mixes configurable
   - Extend mix file schema (or add a second file) to define tool weights.
   - Implement weighted task selection per consumer iteration.

3. Improve live-run signal
   - Add block-page detection heuristics and classify these outcomes distinctly.
   - Include response size and content-type in metrics.

4. Add a "realistic" scenario suite
   - Keep current load scenario.
   - Add:
     - rate-limit scenario (bursting to provoke 429 and measure recovery)
     - session lifecycle scenario (create -> read -> list -> delete/expire)

5. Optional: increase fidelity of recording
   - Record more than just index.html for each site (follow internal links up to depth 1 with a cap).
   - Record assets only if needed for parser behavior (many parsers do not require assets).

## Getting going (practical commands)

Below are minimal commands that work with the current implementation.

1) Run CI-safe fixture-mode load test (no MCP server)

- Uses the built-in fixture server with test fixtures.

Command:

- uv run python simulator/run.py --mode fixture --consumers 4 --rate 2.0 --total-requests 20 --output artifacts/sim_report.json

2) Run MCP auth-groups scenario (requires running MCP service)

Pre-reqs:

- The gofr-dig MCP server must be running and reachable at a docker-network URL like http://gofr-dig-mcp:8070/mcp
- Vault must be reachable if you want the simulator to mint tokens (TokenFactory). If not, supply tokens via env.

Command:

- uv run python simulator/run.py --scenario auth-groups --mode live --mcp-url http://gofr-dig-mcp:8070/mcp

3) Record fixtures (manual, networked)

Command:

- uv run python simulator/run.py --mode record --sites-file simulator/sites.json --record-output-dir simulator/fixtures/data

Notes:

- After recording, you must manually point fixture-mode at the recorded fixtures directory (currently default fixture mode still points to test/fixtures/html).

## Notes and minor observations

- simulator/run.py help text says "record is added in later phases" but record mode is implemented.
- The provider uses randomness without a CLI seed. This makes live test runs harder to reproduce. Consider adding --seed.
- The consumer logs per-request at info level. For high rates this will be extremely noisy and may distort performance; consider dialing per-request logs down to debug in load scenarios.
- tests use fixture mode without MCP, which is good for CI. The auth_groups scenario uses MCP and is appropriate for targeted integration, but likely not appropriate for default CI.
