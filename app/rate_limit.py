"""Inbound rate limiting for MCP tool calls.

Provides a configurable per-identity rate limiter that caps the number
of tool calls per time window.  Identity is resolved from the auth token
(group) or falls back to a shared "anonymous" bucket.

Configuration via environment variables:
    GOFR_DIG_RATE_LIMIT_CALLS  – max calls per window  (default 60)
    GOFR_DIG_RATE_LIMIT_WINDOW – window size in seconds (default 60)
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

from app.logger import session_logger as logger


@dataclass
class _Bucket:
    """Sliding-window counter for one identity."""

    timestamps: list[float] = field(default_factory=list)


class RateLimiter:
    """Sliding-window rate limiter keyed by identity string.

    Thread-safe via a simple lock (MCP server is async but tool dispatch
    is serialised per connection, so contention is minimal).
    """

    def __init__(
        self,
        max_calls: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        self.max_calls = max_calls or int(
            os.environ.get("GOFR_DIG_RATE_LIMIT_CALLS", "60")
        )
        self.window_seconds = window_seconds or int(
            os.environ.get("GOFR_DIG_RATE_LIMIT_WINDOW", "60")
        )
        self._buckets: dict[str, _Bucket] = defaultdict(_Bucket)
        self._lock = Lock()

    def check(self, identity: str | None = None) -> tuple[bool, dict[str, int]]:
        """Check whether a request from *identity* is allowed.

        Args:
            identity: Caller identity (group name or None for anonymous).

        Returns:
            Tuple of (allowed, info) where info contains:
                remaining: calls left in current window
                limit: configured max calls
                reset_seconds: seconds until oldest entry expires
        """
        key = identity or "__anonymous__"
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._buckets[key]
            # Prune expired entries
            bucket.timestamps = [t for t in bucket.timestamps if t > cutoff]

            remaining = self.max_calls - len(bucket.timestamps)
            reset_seconds = (
                int(bucket.timestamps[0] - cutoff + 1) if bucket.timestamps else 0
            )

            if remaining <= 0:
                logger.warning(
                    "Rate limit exceeded",
                    identity=key,
                    limit=self.max_calls,
                    window=self.window_seconds,
                )
                return False, {
                    "remaining": 0,
                    "limit": self.max_calls,
                    "reset_seconds": reset_seconds,
                }

            # Record this call
            bucket.timestamps.append(now)
            return True, {
                "remaining": remaining - 1,
                "limit": self.max_calls,
                "reset_seconds": reset_seconds,
            }


# Module-level singleton
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Return the global rate limiter (created on first call)."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the global rate limiter (for testing)."""
    global _rate_limiter
    _rate_limiter = None
