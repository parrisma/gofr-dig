from __future__ import annotations

from typing import Any

from simulator.core.models import SimulationConfig, SimulationResult


def build_simulation_report(config: SimulationConfig, result: SimulationResult) -> dict[str, Any]:
    config_payload = {
        "mode": config.mode.value,
        "consumers": config.consumers,
        "rate_per_consumer_per_sec": config.rate_per_consumer_per_sec,
        "total_requests": config.total_requests,
        "duration_seconds": config.duration_seconds,
        "mcp_url": config.mcp_url,
        "sites_file": config.sites_file,
        "target_url": config.target_url,
        "timeout_seconds": config.timeout_seconds,
    }
    return {
        "config": config_payload,
        "result": {
            "request_count": result.request_count,
            "error_count": result.error_count,
            "duration_seconds": result.duration_seconds,
            "throughput_rps": result.throughput_rps,
        },
        "metrics": result.metrics_report,
    }
