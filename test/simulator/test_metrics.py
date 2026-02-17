from __future__ import annotations

import pytest

from simulator.core.metrics import MetricsCollector


@pytest.mark.asyncio
async def test_metrics_collector_percentiles_and_grouping():
    collector = MetricsCollector(sample_size=50)

    durations = [10, 20, 30, 40, 50]
    for d in durations:
        await collector.record(
            tool_name="mcp.get_content",
            duration_ms=d,
            success=True,
            persona="apac",
        )

    # Add a failure to ensure error_count is tracked.
    await collector.record(
        tool_name="mcp.get_content",
        duration_ms=60,
        success=False,
        persona="apac",
        error_type="mcp_tool_failed",
    )

    report = await collector.build_report()

    assert report["overall"]["count"] == 6
    assert report["overall"]["error_count"] == 1

    by_tool = report["by_tool"]["mcp.get_content"]
    assert by_tool["count"] == 6
    assert by_tool["error_count"] == 1

    by_tool_persona = report["by_tool_persona"]["mcp.get_content::apac"]
    assert by_tool_persona["count"] == 6
    assert by_tool_persona["error_count"] == 1

    # Values are [10,20,30,40,50,60] => median is (30+40)/2 = 35.
    assert by_tool_persona["p50_ms"] == 35.0

    # Error analysis: verify error_rate_pct and error_types breakdown.
    overall = report["overall"]
    assert overall["error_rate_pct"] == pytest.approx(16.67, abs=0.01)
    assert overall["error_types"] == {"mcp_tool_failed": 1}

    # Per-tool error breakdown should match.
    assert by_tool["error_types"] == {"mcp_tool_failed": 1}
    assert by_tool["error_rate_pct"] == pytest.approx(16.67, abs=0.01)
