"""Load scenario: high-concurrency simulation against fixture or live targets.

This module provides a pre-built ``SimulationConfig`` and convenience
runner for the "load" scenario.  It exercises the system with many
concurrent consumers at sustained throughput to surface stability
issues, memory leaks, or 500 errors.

Usage from CLI::

    uv run python simulator/run.py \\
        --mode fixture --consumers 50 --rate 10.0 --duration 60s

Usage as library::

    from simulator.scenarios.load import build_load_config, run_load_scenario

    result = await run_load_scenario(consumers=50, rate=10.0, duration_seconds=60)
"""

from __future__ import annotations

from simulator.core.engine import Simulator
from simulator.core.models import Mode, SimulationConfig, SimulationResult


def build_load_config(
    *,
    consumers: int = 50,
    rate_per_consumer: float = 10.0,
    duration_seconds: float | None = 60.0,
    total_requests: int | None = None,
    mode: Mode = Mode.FIXTURE,
    mcp_url: str | None = None,
    fixtures_dir: str = "test/fixtures/html",
    timeout_seconds: float = 30.0,
) -> SimulationConfig:
    """Build a ``SimulationConfig`` tuned for load testing.

    By default runs in fixture mode for CI safety.  Pass ``mode=Mode.LIVE``
    and ``mcp_url`` for a real-traffic load test.
    """
    return SimulationConfig(
        mode=mode,
        consumers=consumers,
        rate_per_consumer_per_sec=rate_per_consumer,
        total_requests=total_requests,
        duration_seconds=duration_seconds,
        mcp_url=mcp_url,
        sites_file="simulator/sites.json",
        target_url=None,
        timeout_seconds=timeout_seconds,
    )


async def run_load_scenario(
    *,
    consumers: int = 50,
    rate: float = 10.0,
    duration_seconds: float | None = 60.0,
    total_requests: int | None = None,
    mode: Mode = Mode.FIXTURE,
    mcp_url: str | None = None,
    fixtures_dir: str = "test/fixtures/html",
    mix_file: str | None = None,
    timeout_seconds: float = 30.0,
) -> SimulationResult:
    """Run a load scenario and return the result.

    This is the programmatic entry point used by integration tests and CI.
    """
    config = build_load_config(
        consumers=consumers,
        rate_per_consumer=rate,
        duration_seconds=duration_seconds,
        total_requests=total_requests,
        mode=mode,
        mcp_url=mcp_url,
        fixtures_dir=fixtures_dir,
        timeout_seconds=timeout_seconds,
    )
    sim = Simulator(config, fixtures_dir=fixtures_dir, mix_file=mix_file)
    return await sim.run()
