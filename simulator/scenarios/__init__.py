"""Pre-built simulation scenarios."""

from __future__ import annotations

__all__ = ["run_load_scenario", "build_load_config", "run_auth_groups_scenario"]

from simulator.scenarios.load import build_load_config, run_load_scenario
from simulator.scenarios.auth_groups import run_auth_groups_scenario
