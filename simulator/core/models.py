from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Mode(str, Enum):
    """Simulation execution mode.

    live: hit real internet URLs from sites.json (manual/nightly)
    fixture: hit local fixture server URLs (CI-safe) — implemented in later phases
    record: capture live content and obfuscate to fixtures — implemented in later phases
    """

    LIVE = "live"
    FIXTURE = "fixture"
    RECORD = "record"


class TokenType(str, Enum):
    """Authentication token behavior for a persona."""

    NONE = "none"  # anonymous
    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"


@dataclass(frozen=True)
class Persona:
    """Consumer persona.

    Phase 1 uses only HTTP GET and does not apply auth.
    Later phases use these fields to mint tokens and validate group isolation.
    """

    name: str
    group: str | None
    token_type: TokenType


@dataclass(frozen=True)
class Task:
    """A single unit of work for a consumer.

    Later phases will represent MCP tool calls (tool_name + args).
    """

    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class SimulationConfig:
    mode: Mode
    consumers: int
    rate_per_consumer_per_sec: float
    total_requests: int | None
    duration_seconds: float | None
    mcp_url: str | None
    sites_file: str
    target_url: str | None
    timeout_seconds: float


@dataclass
class SimulationResult:
    started_at_monotonic: float
    ended_at_monotonic: float
    request_count: int
    error_count: int
    metrics_report: dict[str, Any] | None = None

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.ended_at_monotonic - self.started_at_monotonic)

    @property
    def throughput_rps(self) -> float:
        duration = self.duration_seconds
        return (self.request_count / duration) if duration > 0 else 0.0
