"""Auto-incrementing build number derived from git.

Format: "{commit_count}.{short_hash}" e.g. "16.33b6184"

Resolution order:
1. GOFR_DIG_BUILD_NUMBER env var (set at Docker build time)
2. Live git query (dev / non-Docker)
3. "0.unknown" fallback
"""

import os
import subprocess


def _git_build_number() -> str:
    """Derive build number from git history."""
    try:
        count = (
            subprocess.check_output(
                ["git", "rev-list", "--count", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        short_hash = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        return f"{count}.{short_hash}"
    except Exception:
        return "0.unknown"


BUILD_NUMBER: str = os.environ.get("GOFR_DIG_BUILD_NUMBER") or _git_build_number()
