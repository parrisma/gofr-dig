"""Tests for the load scenario module."""

from __future__ import annotations

import pytest

from simulator.core.models import Mode
from simulator.scenarios.load import build_load_config, run_load_scenario


class TestBuildLoadConfig:
    """Config builder tests."""

    def test_defaults(self):
        config = build_load_config()
        assert config.consumers == 50
        assert config.rate_per_consumer_per_sec == 10.0
        assert config.duration_seconds == 60.0
        assert config.mode == Mode.FIXTURE
        assert config.mcp_url is None

    def test_custom_values(self):
        config = build_load_config(
            consumers=10,
            rate_per_consumer=5.0,
            duration_seconds=30.0,
            mode=Mode.LIVE,
            mcp_url="http://mcp:8070/mcp",
        )
        assert config.consumers == 10
        assert config.rate_per_consumer_per_sec == 5.0
        assert config.duration_seconds == 30.0
        assert config.mode == Mode.LIVE
        assert config.mcp_url == "http://mcp:8070/mcp"

    def test_total_requests_override(self):
        config = build_load_config(total_requests=100, duration_seconds=0)
        assert config.total_requests == 100


class TestRunLoadScenario:
    """Run the load scenario as a library (fixture mode, small scale)."""

    @pytest.mark.asyncio
    async def test_small_load_run(self):
        """Run a tiny load scenario and verify results."""
        result = await run_load_scenario(
            consumers=3,
            rate=50.0,
            duration_seconds=None,
            total_requests=9,
            fixtures_dir="test/fixtures/html",
        )
        assert result.request_count == 9
        assert result.error_count == 0
        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_duration_based_load(self):
        """Run a duration-based load and verify completion."""
        result = await run_load_scenario(
            consumers=2,
            rate=20.0,
            duration_seconds=0.3,
            total_requests=None,
            fixtures_dir="test/fixtures/html",
        )
        assert result.request_count > 0
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_higher_concurrency(self):
        """Run with more consumers to stress the engine."""
        result = await run_load_scenario(
            consumers=10,
            rate=50.0,
            duration_seconds=None,
            total_requests=50,
            fixtures_dir="test/fixtures/html",
        )
        assert result.request_count == 50
        assert result.error_count == 0
        assert result.metrics_report is not None
        assert result.metrics_report["overall"]["count"] == 50
