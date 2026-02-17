from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MixEntry:
    name: str
    count: int
    token: str | None


@dataclass(frozen=True)
class MixConfig:
    entries: list[MixEntry]

    @property
    def total_consumers(self) -> int:
        return sum(e.count for e in self.entries)


def load_mix_file(path: str) -> MixConfig:
    """Load a consumer mix definition.

    Expected shape:
      {
        "groups": {
          "apac": {"count": 5, "token": "token_apac"},
          "emea": {"count": 5, "token": "token_emea"},
          "us":   {"count": 5, "token": "token_us"},
          "multi": {"count": 1, "token": "token_multi"},
          "public": {"count": 2, "token": null},
          "attacker": {"count": 1, "token": "token_invalid"}
        }
      }

    `token` is either:
      - null (anonymous)
      - a literal JWT string
      - a symbolic name like token_apac/token_multi/token_invalid/token_expired
    """

    mix_path = Path(path)
    data = json.loads(mix_path.read_text(encoding="utf-8"))

    groups = data.get("groups")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("mix file must contain a non-empty 'groups' object")

    entries: list[MixEntry] = []
    for name, raw in groups.items():
        if not isinstance(raw, dict):
            raise ValueError(f"mix entry {name!r} must be an object")

        count = raw.get("count")
        token = raw.get("token")

        if not isinstance(count, int) or count < 0:
            raise ValueError(f"mix entry {name!r} has invalid count: {count!r}")

        if token is not None and not isinstance(token, str):
            raise ValueError(f"mix entry {name!r} token must be a string or null")

        if count == 0:
            continue

        entries.append(MixEntry(name=str(name), count=count, token=token))

    if not entries:
        raise ValueError("mix file must include at least one entry with count > 0")

    return MixConfig(entries=entries)
