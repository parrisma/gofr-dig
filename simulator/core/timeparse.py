from __future__ import annotations

import re


_DURATION_RE = re.compile(r"^(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h)$")


def parse_duration_to_seconds(raw: str) -> float:
    """Parse duration strings like '500ms', '10s', '5m', '1h' into seconds."""
    match = _DURATION_RE.match(raw.strip())
    if not match:
        raise ValueError("duration must match <number><unit> where unit is ms|s|m|h")

    value = float(match.group("value"))
    unit = match.group("unit")

    if value < 0:
        raise ValueError("duration must be non-negative")

    if unit == "ms":
        return value / 1000.0
    if unit == "s":
        return value
    if unit == "m":
        return value * 60.0
    if unit == "h":
        return value * 3600.0

    raise ValueError("unsupported duration unit")
