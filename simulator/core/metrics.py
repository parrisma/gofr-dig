from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass, field
from typing import Any

from app.logger import Logger, session_logger


def _percentile(sorted_values: list[int], p: float) -> float | None:
    """Compute percentile using linear interpolation.

    Expects sorted_values sorted ascending.
    """

    if not sorted_values:
        return None

    if p <= 0:
        return float(sorted_values[0])
    if p >= 1:
        return float(sorted_values[-1])

    k = (len(sorted_values) - 1) * p
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return float(sorted_values[f])
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return float(d0 + d1)


class _ReservoirSampler:
    """Fixed-size reservoir sampler for latency values.

    This avoids unbounded memory growth during long simulation runs.
    """

    def __init__(self, max_size: int, *, seed: int | None = None) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be > 0")
        self._max_size = max_size
        self._rng = random.Random(seed)
        self._seen = 0
        self._values: list[int] = []

    def add(self, value: int) -> None:
        self._seen += 1
        if len(self._values) < self._max_size:
            self._values.append(value)
            return

        # Replace elements with decreasing probability.
        idx = self._rng.randrange(self._seen)
        if idx < self._max_size:
            self._values[idx] = value

    def values(self) -> list[int]:
        return list(self._values)


@dataclass
class _LatencyAgg:
    count: int = 0
    error_count: int = 0
    sum_ms: int = 0
    min_ms: int | None = None
    max_ms: int | None = None
    error_types: dict[str, int] = field(default_factory=dict)


class MetricsCollector:
    """Collects per-tool/per-persona metrics for simulator runs."""

    def __init__(
        self,
        *,
        sample_size: int = 5000,
        logger: Logger | None = None,
    ) -> None:
        self._logger = logger or session_logger
        self._lock = asyncio.Lock()

        self._sample_size = sample_size
        self._overall = _LatencyAgg()
        self._overall_sample = _ReservoirSampler(sample_size)

        self._by_tool: dict[str, _LatencyAgg] = {}
        self._by_tool_sample: dict[str, _ReservoirSampler] = {}

        # Key: (tool, persona)
        self._by_tool_persona: dict[tuple[str, str], _LatencyAgg] = {}
        self._by_tool_persona_sample: dict[tuple[str, str], _ReservoirSampler] = {}

    async def record(
        self,
        *,
        tool_name: str,
        duration_ms: int,
        success: bool,
        persona: str | None = None,
        error_type: str | None = None,
    ) -> None:
        """Record a single tool call/operation."""

        if duration_ms < 0:
            duration_ms = 0

        persona_name = persona or "default"

        async with self._lock:
            self._observe(self._overall, self._overall_sample, duration_ms, success, error_type)

            tool_agg = self._by_tool.get(tool_name)
            if tool_agg is None:
                tool_agg = _LatencyAgg()
                self._by_tool[tool_name] = tool_agg
                self._by_tool_sample[tool_name] = _ReservoirSampler(self._sample_size)
            self._observe(tool_agg, self._by_tool_sample[tool_name], duration_ms, success, error_type)

            key = (tool_name, persona_name)
            tp_agg = self._by_tool_persona.get(key)
            if tp_agg is None:
                tp_agg = _LatencyAgg()
                self._by_tool_persona[key] = tp_agg
                self._by_tool_persona_sample[key] = _ReservoirSampler(self._sample_size)
            self._observe(tp_agg, self._by_tool_persona_sample[key], duration_ms, success, error_type)

        if not success and error_type:
            self._logger.debug(
                "sim.metric_error_recorded",
                event="sim.metric_error_recorded",
                tool_name=tool_name,
                persona=persona_name,
                error_type=error_type,
            )

    async def build_report(self) -> dict[str, Any]:
        async with self._lock:
            overall = self._agg_to_report(self._overall, self._overall_sample)

            tools: dict[str, Any] = {}
            for tool_name, agg in self._by_tool.items():
                tools[tool_name] = self._agg_to_report(agg, self._by_tool_sample[tool_name])

            tool_persona: dict[str, Any] = {}
            for (tool_name, persona), agg in self._by_tool_persona.items():
                key = f"{tool_name}::{persona}"
                tool_persona[key] = self._agg_to_report(agg, self._by_tool_persona_sample[(tool_name, persona)])

            return {
                "overall": overall,
                "by_tool": tools,
                "by_tool_persona": tool_persona,
            }

    def _observe(
        self,
        agg: _LatencyAgg,
        sample: _ReservoirSampler,
        duration_ms: int,
        success: bool,
        error_type: str | None = None,
    ) -> None:
        agg.count += 1
        if not success:
            agg.error_count += 1
            et = error_type or "unknown"
            agg.error_types[et] = agg.error_types.get(et, 0) + 1
        agg.sum_ms += duration_ms
        if agg.min_ms is None or duration_ms < agg.min_ms:
            agg.min_ms = duration_ms
        if agg.max_ms is None or duration_ms > agg.max_ms:
            agg.max_ms = duration_ms
        sample.add(duration_ms)

    def _agg_to_report(self, agg: _LatencyAgg, sample: _ReservoirSampler) -> dict[str, Any]:
        values = sample.values()
        values.sort()

        p50 = _percentile(values, 0.50)
        p95 = _percentile(values, 0.95)
        p99 = _percentile(values, 0.99)

        mean = (agg.sum_ms / agg.count) if agg.count else None
        error_rate = (agg.error_count / agg.count * 100) if agg.count else 0.0
        return {
            "count": agg.count,
            "error_count": agg.error_count,
            "error_rate_pct": round(error_rate, 2),
            "error_types": dict(agg.error_types) if agg.error_types else {},
            "min_ms": agg.min_ms,
            "max_ms": agg.max_ms,
            "mean_ms": mean,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "sample_size": len(values),
        }
