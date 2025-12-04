"""Robots.txt parsing and compliance.

This module provides robots.txt fetching, parsing, and URL checking
to ensure scraping operations respect site policies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.logger import session_logger as logger


@dataclass
class RobotRule:
    """A single robots.txt rule.

    Attributes:
        path: The path pattern
        allow: True if this is an Allow rule, False for Disallow
    """

    path: str
    allow: bool

    def matches(self, url_path: str) -> bool:
        """Check if this rule matches a URL path.

        Supports * wildcard and $ end anchor.
        """
        pattern = self.path

        # Handle empty disallow (means allow all)
        if not pattern:
            return self.allow

        # Convert robots.txt pattern to regex
        # Escape special regex chars except * and $
        regex_pattern = ""
        i = 0
        while i < len(pattern):
            char = pattern[i]
            if char == "*":
                regex_pattern += ".*"
            elif char == "$" and i == len(pattern) - 1:
                regex_pattern += "$"
            elif char in r"\.+?{}[]()^|":
                regex_pattern += "\\" + char
            else:
                regex_pattern += char
            i += 1

        # If pattern doesn't end with $ or *, it's a prefix match
        if not pattern.endswith("$") and not pattern.endswith("*"):
            regex_pattern += ".*"

        try:
            return bool(re.match(regex_pattern, url_path))
        except re.error:
            # If regex fails, fall back to prefix match
            return url_path.startswith(pattern.rstrip("*$"))


@dataclass
class RobotRules:
    """Rules for a specific user-agent.

    Attributes:
        user_agent: The user-agent pattern these rules apply to
        rules: List of rules in order
        crawl_delay: Crawl delay in seconds, if specified
    """

    user_agent: str
    rules: List[RobotRule] = field(default_factory=list)
    crawl_delay: Optional[float] = None

    def is_allowed(self, url_path: str) -> bool:
        """Check if a URL path is allowed by these rules.

        Uses most-specific-match-wins: the rule with the longest
        matching path determines the result. If paths are equal length,
        Allow takes precedence over Disallow.
        """
        best_match: Optional[RobotRule] = None
        best_match_length = -1

        for rule in self.rules:
            if rule.matches(url_path):
                # Calculate effective match length
                match_length = len(rule.path.rstrip("*$"))

                # More specific (longer) matches win
                # If equal length, Allow beats Disallow
                if match_length > best_match_length or (
                    match_length == best_match_length
                    and best_match is not None
                    and rule.allow
                    and not best_match.allow
                ):
                    best_match = rule
                    best_match_length = match_length

        if best_match is not None:
            return best_match.allow

        return True  # Default allow if no rules match


@dataclass
class RobotsFile:
    """Parsed robots.txt file.

    Attributes:
        url: URL of the robots.txt file
        rules_by_agent: Rules grouped by user-agent
        sitemaps: List of sitemap URLs
        raw_content: Original robots.txt content
    """

    url: str
    rules_by_agent: Dict[str, RobotRules] = field(default_factory=dict)
    sitemaps: List[str] = field(default_factory=list)
    raw_content: str = ""

    def get_rules_for_agent(self, user_agent: str) -> RobotRules:
        """Get rules for a specific user-agent.

        Tries exact match first, then * wildcard.
        """
        # Normalize user-agent
        ua_lower = user_agent.lower()

        # Try exact match
        for pattern, rules in self.rules_by_agent.items():
            if pattern.lower() == ua_lower:
                return rules

        # Try prefix match (e.g., "Googlebot" matches "Googlebot/2.1")
        for pattern, rules in self.rules_by_agent.items():
            if ua_lower.startswith(pattern.lower()):
                return rules

        # Fall back to * rules
        if "*" in self.rules_by_agent:
            return self.rules_by_agent["*"]

        # No rules found - return empty rules (allow all)
        return RobotRules(user_agent="*")

    def is_allowed(self, url: str, user_agent: str = "*") -> bool:
        """Check if a URL is allowed for a user-agent.

        Args:
            url: Full URL to check
            user_agent: User-agent string

        Returns:
            True if allowed, False if disallowed
        """
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        rules = self.get_rules_for_agent(user_agent)
        return rules.is_allowed(path)

    def get_crawl_delay(self, user_agent: str = "*") -> Optional[float]:
        """Get crawl delay for a user-agent."""
        rules = self.get_rules_for_agent(user_agent)
        return rules.crawl_delay


class RobotsParser:
    """Parser for robots.txt files."""

    def parse(self, content: str, url: str = "") -> RobotsFile:
        """Parse robots.txt content.

        Args:
            content: Raw robots.txt content
            url: URL of the robots.txt file

        Returns:
            Parsed RobotsFile
        """
        robots = RobotsFile(url=url, raw_content=content)

        current_agents: List[str] = []
        current_rules: List[RobotRule] = []
        current_crawl_delay: Optional[float] = None

        def save_current_group():
            """Save the current group of rules."""
            if current_agents and current_rules:
                for agent in current_agents:
                    robots.rules_by_agent[agent] = RobotRules(
                        user_agent=agent,
                        rules=current_rules.copy(),
                        crawl_delay=current_crawl_delay,
                    )

        for line in content.splitlines():
            # Remove comments
            if "#" in line:
                line = line[: line.index("#")]
            line = line.strip()

            if not line:
                continue

            # Parse directive
            if ":" not in line:
                continue

            directive, value = line.split(":", 1)
            directive = directive.strip().lower()
            value = value.strip()

            if directive == "user-agent":
                # New user-agent starts a new group
                if current_rules:
                    save_current_group()
                    current_rules = []
                    current_crawl_delay = None
                    current_agents = []
                current_agents.append(value)

            elif directive == "disallow":
                current_rules.append(RobotRule(path=value, allow=False))

            elif directive == "allow":
                current_rules.append(RobotRule(path=value, allow=True))

            elif directive == "crawl-delay":
                try:
                    current_crawl_delay = float(value)
                except ValueError:
                    pass

            elif directive == "sitemap":
                robots.sitemaps.append(value)

        # Save final group
        save_current_group()

        return robots


class RobotsChecker:
    """Check URLs against robots.txt with caching."""

    def __init__(self):
        """Initialize the robots checker."""
        self._cache: Dict[str, RobotsFile] = {}
        self._parser = RobotsParser()

    def get_robots_url(self, url: str) -> str:
        """Get the robots.txt URL for a given URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    async def fetch_robots(self, url: str) -> Optional[RobotsFile]:
        """Fetch and parse robots.txt for a URL.

        Args:
            url: Any URL on the site

        Returns:
            Parsed RobotsFile or None if not found/error
        """
        robots_url = self.get_robots_url(url)

        # Check cache
        if robots_url in self._cache:
            return self._cache[robots_url]

        # Fetch robots.txt - use minimal headers
        # Use minimal headers for robots.txt
        from app.scraping.antidetection import AntiDetectionManager, AntiDetectionProfile

        manager = AntiDetectionManager(AntiDetectionProfile.NONE)

        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=10.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    robots_url,
                    headers=manager.get_headers(),
                    allow_redirects=True,
                ) as response:
                    if response.status == 200:
                        content = await response.text()
                        robots = self._parser.parse(content, robots_url)
                        self._cache[robots_url] = robots
                        logger.debug("Fetched robots.txt", url=robots_url)
                        return robots
                    else:
                        # No robots.txt or error - allow all
                        logger.debug(
                            "No robots.txt found",
                            url=robots_url,
                            status=response.status,
                        )
                        robots = RobotsFile(url=robots_url)
                        self._cache[robots_url] = robots
                        return robots

        except Exception as e:
            logger.warning("Failed to fetch robots.txt", url=robots_url, error=str(e))
            # On error, cache empty robots (allow all)
            robots = RobotsFile(url=robots_url)
            self._cache[robots_url] = robots
            return robots

    async def is_allowed(
        self,
        url: str,
        user_agent: str = "*",
    ) -> Tuple[bool, Optional[str]]:
        """Check if a URL is allowed by robots.txt.

        Args:
            url: URL to check
            user_agent: User-agent string

        Returns:
            Tuple of (is_allowed, reason)
        """
        robots = await self.fetch_robots(url)

        if robots is None:
            return True, None

        allowed = robots.is_allowed(url, user_agent)

        if not allowed:
            return False, f"Disallowed by robots.txt for {user_agent}"

        return True, None

    async def get_crawl_delay(self, url: str, user_agent: str = "*") -> Optional[float]:
        """Get crawl delay from robots.txt.

        Args:
            url: Any URL on the site
            user_agent: User-agent string

        Returns:
            Crawl delay in seconds, or None
        """
        robots = await self.fetch_robots(url)
        if robots:
            return robots.get_crawl_delay(user_agent)
        return None

    def clear_cache(self):
        """Clear the robots.txt cache."""
        self._cache.clear()


# Global checker instance
_checker: Optional[RobotsChecker] = None


def get_robots_checker() -> RobotsChecker:
    """Get the global robots checker instance."""
    global _checker
    if _checker is None:
        _checker = RobotsChecker()
    return _checker


def reset_robots_checker() -> None:
    """Reset the global robots checker."""
    global _checker
    if _checker:
        _checker.clear_cache()
    _checker = None
