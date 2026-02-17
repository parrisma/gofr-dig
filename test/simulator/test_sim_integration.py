"""Integration tests for the Simulator engine.

These tests exercise the Simulator as a library in fixture mode
(no real network traffic, no MCP server dependency) and validate
that SimulationResult fields are sane.
"""

from __future__ import annotations

import pytest

from simulator.core.engine import Simulator
from simulator.core.models import Mode, SimulationConfig


_FIXTURES_DIR = "test/fixtures/html"


def _make_config(
    *,
    consumers: int = 2,
    rate: float = 10.0,
    total_requests: int | None = 4,
    duration_seconds: float | None = None,
) -> SimulationConfig:
    return SimulationConfig(
        mode=Mode.FIXTURE,
        consumers=consumers,
        rate_per_consumer_per_sec=rate,
        total_requests=total_requests,
        duration_seconds=duration_seconds,
        mcp_url=None,
        sites_file="simulator/sites.json",
        target_url=None,
        timeout_seconds=10.0,
    )


class TestSimulatorIntegration:
    """Library-level integration tests for the Simulator."""

    @pytest.mark.asyncio
    async def test_fixture_mode_completes(self):
        """Simulator runs in fixture mode and returns a valid result."""
        config = _make_config(consumers=2, total_requests=4)
        sim = Simulator(config, fixtures_dir=_FIXTURES_DIR)
        result = await sim.run()

        assert result.request_count == 4
        assert result.error_count == 0
        assert result.duration_seconds > 0
        assert result.throughput_rps > 0

    @pytest.mark.asyncio
    async def test_single_consumer_single_request(self):
        """Minimal run: 1 consumer, 1 request."""
        config = _make_config(consumers=1, total_requests=1, rate=5.0)
        sim = Simulator(config, fixtures_dir=_FIXTURES_DIR)
        result = await sim.run()

        assert result.request_count == 1
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_duration_based_stop(self):
        """Simulator stops after the configured duration."""
        config = _make_config(
            consumers=1,
            total_requests=None,
            duration_seconds=0.5,
            rate=20.0,
        )
        sim = Simulator(config, fixtures_dir=_FIXTURES_DIR)
        result = await sim.run()

        # Should have completed some requests within 0.5s at 20 req/s
        assert result.request_count > 0
        assert result.error_count == 0
        assert result.duration_seconds >= 0.4  # allow small timing slack

    @pytest.mark.asyncio
    async def test_multiple_consumers_share_budget(self):
        """Multiple consumers collectively consume the total request budget."""
        config = _make_config(consumers=3, total_requests=9, rate=50.0)
        sim = Simulator(config, fixtures_dir=_FIXTURES_DIR)
        result = await sim.run()

        assert result.request_count == 9
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_metrics_report_populated(self):
        """Metrics report is present and contains expected keys."""
        config = _make_config(consumers=2, total_requests=4, rate=50.0)
        sim = Simulator(config, fixtures_dir=_FIXTURES_DIR)
        result = await sim.run()

        report = result.metrics_report
        assert report is not None
        assert "overall" in report
        assert report["overall"]["count"] == 4
        assert report["overall"]["error_count"] == 0
        assert "by_tool" in report
        assert "http.get" in report["by_tool"]

    @pytest.mark.asyncio
    async def test_mix_file_fixture_mode(self, tmp_path):
        """Simulator with a mix file in fixture mode (no MCP, plain HTTP)."""
        import json

        mix = {
            "groups": {
                "group_a": {"count": 1, "token": None},
                "group_b": {"count": 1, "token": None},
            }
        }
        mix_path = tmp_path / "mix.json"
        mix_path.write_text(json.dumps(mix), encoding="utf-8")

        config = SimulationConfig(
            mode=Mode.FIXTURE,
            consumers=0,
            rate_per_consumer_per_sec=50.0,
            total_requests=4,
            duration_seconds=None,
            mcp_url=None,
            sites_file="simulator/sites.json",
            target_url=None,
            timeout_seconds=10.0,
        )
        sim = Simulator(config, fixtures_dir=_FIXTURES_DIR, mix_file=str(mix_path))
        result = await sim.run()

        assert result.request_count == 4
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_result_throughput_reasonable(self):
        """Throughput calculation is consistent with request count and duration."""
        config = _make_config(consumers=1, total_requests=5, rate=100.0)
        sim = Simulator(config, fixtures_dir=_FIXTURES_DIR)
        result = await sim.run()

        # throughput = requests / duration
        expected_rps = result.request_count / result.duration_seconds
        assert abs(result.throughput_rps - expected_rps) < 0.01

    @pytest.mark.asyncio
    async def test_zero_consumers_without_mix_raises(self):
        """Engine rejects 0 consumers when no mix file is provided."""
        config = _make_config(consumers=0, total_requests=1)
        sim = Simulator(config, fixtures_dir=_FIXTURES_DIR)

        with pytest.raises(ValueError, match="consumers must be >= 1"):
            await sim.run()

    @pytest.mark.asyncio
    async def test_missing_stop_condition_raises(self):
        """Engine rejects config with neither total_requests nor duration."""
        config = SimulationConfig(
            mode=Mode.FIXTURE,
            consumers=1,
            rate_per_consumer_per_sec=1.0,
            total_requests=None,
            duration_seconds=None,
            mcp_url=None,
            sites_file="simulator/sites.json",
            target_url=None,
            timeout_seconds=10.0,
        )
        sim = Simulator(config, fixtures_dir=_FIXTURES_DIR)

        with pytest.raises(ValueError, match="total_requests or duration_seconds"):
            await sim.run()
