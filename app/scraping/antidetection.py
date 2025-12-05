"""Anti-detection configuration and header generation.

This module provides anti-detection capabilities for web scraping,
including User-Agent rotation, browser-like headers, and configurable
profiles for different scraping scenarios.
"""

from __future__ import annotations

import random
from enum import Enum
from typing import Dict, List, Optional


class AntiDetectionProfile(str, Enum):
    """Anti-detection profile presets.

    - STEALTH: Maximum anti-detection with full browser emulation
    - BALANCED: Moderate anti-detection suitable for most sites
    - NONE: No anti-detection, bare minimum headers
    - CUSTOM: User-defined headers and settings
    - BROWSER_TLS: Uses curl_cffi to impersonate browser TLS fingerprint
                   (bypasses TLS fingerprinting detection like Wikipedia)
    """

    STEALTH = "stealth"
    BALANCED = "balanced"
    NONE = "none"
    CUSTOM = "custom"
    BROWSER_TLS = "browser_tls"


# Common User-Agent strings for rotation
# These represent real browser user agents from 2024
USER_AGENTS: List[str] = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    # Firefox on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


# Accept headers by content type
ACCEPT_HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
ACCEPT_JSON = "application/json, text/plain, */*"
ACCEPT_LANGUAGE = "en-US,en;q=0.9"
ACCEPT_ENCODING = "gzip, deflate, br"


class AntiDetectionManager:
    """Manager for anti-detection settings and header generation.

    This class provides methods to generate appropriate HTTP headers
    based on the configured anti-detection profile.

    Example:
        manager = AntiDetectionManager(AntiDetectionProfile.STEALTH)
        headers = manager.get_headers()
        # Use headers in HTTP requests
    """

    def __init__(
        self,
        profile: AntiDetectionProfile = AntiDetectionProfile.BALANCED,
        custom_headers: Optional[Dict[str, str]] = None,
        custom_user_agent: Optional[str] = None,
    ):
        """Initialize the anti-detection manager.

        Args:
            profile: Anti-detection profile to use
            custom_headers: Custom headers for CUSTOM profile
            custom_user_agent: Custom User-Agent for CUSTOM profile
        """
        self.profile = profile
        self.custom_headers = custom_headers or {}
        self.custom_user_agent = custom_user_agent
        self._current_user_agent: Optional[str] = None

    def get_user_agent(self, rotate: bool = False) -> str:
        """Get a User-Agent string based on the current profile.

        Args:
            rotate: If True, select a new random User-Agent

        Returns:
            User-Agent string
        """
        if self.profile == AntiDetectionProfile.NONE:
            return "gofr-dig/1.0"

        if self.profile == AntiDetectionProfile.CUSTOM and self.custom_user_agent:
            return self.custom_user_agent

        # For STEALTH and BALANCED, use rotation
        if rotate or self._current_user_agent is None:
            self._current_user_agent = random.choice(USER_AGENTS)

        return self._current_user_agent

    def get_headers(self, rotate_user_agent: bool = False) -> Dict[str, str]:
        """Get HTTP headers based on the current profile.

        Args:
            rotate_user_agent: If True, rotate to a new User-Agent

        Returns:
            Dictionary of HTTP headers
        """
        if self.profile == AntiDetectionProfile.NONE:
            return {
                "User-Agent": self.get_user_agent(),
            }

        if self.profile == AntiDetectionProfile.CUSTOM:
            headers = {"User-Agent": self.get_user_agent()}
            headers.update(self.custom_headers)
            return headers

        # BALANCED profile - standard browser-like headers
        if self.profile == AntiDetectionProfile.BALANCED:
            return {
                "User-Agent": self.get_user_agent(rotate_user_agent),
                "Accept": ACCEPT_HTML,
                "Accept-Language": ACCEPT_LANGUAGE,
                "Accept-Encoding": ACCEPT_ENCODING,
            }

        # STEALTH profile - full browser emulation
        # This includes additional headers that make requests look more like
        # real browser traffic
        return {
            "User-Agent": self.get_user_agent(rotate_user_agent),
            "Accept": ACCEPT_HTML,
            "Accept-Language": ACCEPT_LANGUAGE,
            "Accept-Encoding": ACCEPT_ENCODING,
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Connection": "keep-alive",
        }

    def get_profile_info(self) -> Dict[str, str]:
        """Get information about the current profile.

        Returns:
            Dictionary with profile details
        """
        descriptions = {
            AntiDetectionProfile.STEALTH: "Maximum anti-detection with full browser emulation headers",
            AntiDetectionProfile.BALANCED: "Moderate anti-detection with standard browser headers",
            AntiDetectionProfile.NONE: "No anti-detection, minimal headers",
            AntiDetectionProfile.CUSTOM: "User-defined custom headers",
            AntiDetectionProfile.BROWSER_TLS: "Browser TLS fingerprint impersonation (bypasses TLS fingerprinting)",
        }

        return {
            "profile": self.profile.value,
            "description": descriptions[self.profile],
            "user_agent": self.get_user_agent(),
        }
