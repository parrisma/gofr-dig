"""Global state management for scraping operations.

This module manages the shared state for scraping tools, including
anti-detection settings that persist across tool invocations within
an MCP session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from app.scraping.antidetection import AntiDetectionProfile


@dataclass
class ScrapingState:
    """Global state for scraping operations.

    This state is maintained across tool invocations within an MCP session.
    It stores anti-detection settings and other scraping configuration.

    Attributes:
        antidetection_profile: Current anti-detection profile (stealth/balanced/none/custom)
        custom_headers: Custom headers when using 'custom' profile
        custom_user_agent: Custom User-Agent when using 'custom' profile
        respect_robots_txt: Whether to respect robots.txt (default True)
        rate_limit_delay: Delay in seconds between requests (default 1.0)
    """

    antidetection_profile: AntiDetectionProfile = AntiDetectionProfile.BALANCED
    custom_headers: Dict[str, str] = field(default_factory=dict)
    custom_user_agent: Optional[str] = None
    respect_robots_txt: bool = True
    rate_limit_delay: float = 1.0


# Global singleton instance for the scraping state
# This persists across tool calls within the same MCP server process
_scraping_state: Optional[ScrapingState] = None


def get_scraping_state() -> ScrapingState:
    """Get the global scraping state instance.

    Creates a new instance with default values if one doesn't exist.

    Returns:
        ScrapingState: The global scraping state
    """
    global _scraping_state
    if _scraping_state is None:
        _scraping_state = ScrapingState()
    return _scraping_state


def reset_scraping_state() -> None:
    """Reset the global scraping state to defaults.

    Useful for testing and cleanup.
    """
    global _scraping_state
    _scraping_state = None
