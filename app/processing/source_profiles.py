"""Source profiles for news parser — site-specific configuration.

Profiles are pure data (no code branches). Each profile declares patterns, labels, and
timezone information that the parser uses for noise stripping, date parsing, and content
classification.

Add new profiles by inserting a key into SOURCE_PROFILES dict below.
"""

from __future__ import annotations

SOURCE_PROFILES: dict[str, dict] = {
    "scmp": {
        "name": "scmp",
        "display_name": "South China Morning Post",
        "timezone": "Asia/Hong_Kong",
        "utc_offset": "+08:00",
        "date_patterns": [
            r"\d{1,2}\s+\w+\s+\d{4}\s*-\s*\d{1,2}:\d{2}[AP]M",
            r"\d+\s+(minutes?|hours?)\s+ago",
        ],
        "section_labels": [
            "Business",
            "Tech",
            "China Economy",
            "Banking & Finance",
            "Opinion",
            "Markets",
            "Companies",
            "Property",
            "China",
            "Asia",
            "World",
        ],
        "noise_markers": [
            "TRENDING TOPICS",
            "MOST POPULAR",
            "MORE LATEST NEWS",
            "MORE COMMENT",
        ],
        "sponsored_markers": ["In partnership with:", "Paid Post:"],
        "exclusive_markers": ["Exclusive"],
        "opinion_labels": ["Opinion", "Macroscope", "As I see it"],
    },
}

# Generic fallback profile — used when no source_profile_name is supplied.
GENERIC_PROFILE: dict = {
    "name": "generic",
    "display_name": "Unknown Source",
    "timezone": "UTC",
    "utc_offset": "+00:00",
    "date_patterns": [
        r"\d{1,2}\s+\w+\s+\d{4}\s*-\s*\d{1,2}:\d{2}[AP]M",
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}",
        r"\w+\s+\d{1,2},?\s+\d{4}",
        r"\d+\s+(minutes?|hours?|days?)\s+ago",
    ],
    "section_labels": [],
    "noise_markers": [
        "TRENDING",
        "MOST POPULAR",
        "ADVERTISEMENT",
        "SPONSORED",
    ],
    "sponsored_markers": ["Sponsored:", "Paid Post:", "In partnership with:"],
    "exclusive_markers": ["Exclusive", "EXCLUSIVE"],
    "opinion_labels": ["Opinion", "Editorial", "Commentary"],
}


def get_source_profile(name: str | None) -> dict:
    """Return a source profile by name, or the generic fallback.

    Args:
        name: profile key (e.g. "scmp") or None for generic.

    Returns:
        Profile dict — always contains all required keys.
    """
    if name and name in SOURCE_PROFILES:
        return SOURCE_PROFILES[name]
    return GENERIC_PROFILE.copy()
