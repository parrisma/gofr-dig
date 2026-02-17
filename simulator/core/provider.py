from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Iterable


@dataclass(frozen=True)
class Site:
    name: str
    url: str
    country: str


class SiteProvider:
    """Provides target URLs for consumers.

    Phase 1 supports reading `simulator/sites.json` and returning site home URLs.
    Later phases add fixture/record modes and per-site route patterns.
    """

    def __init__(self, sites: list[Site], *, seed: int | None = None) -> None:
        if not sites:
            raise ValueError("sites list must be non-empty")
        self._sites = sites
        self._rng = Random(seed)

    @staticmethod
    def load_from_file(path: str) -> "SiteProvider":
        sites_file = Path(path)
        data = json.loads(sites_file.read_text(encoding="utf-8"))

        sites: list[Site] = []
        for country, entries in data.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                url = str(entry.get("url", "")).strip()
                name = str(entry.get("name", "")).strip() or url
                if not url:
                    continue
                sites.append(Site(name=name, url=url, country=str(country)))

        if not sites:
            raise ValueError(f"no valid sites found in {path}")

        return SiteProvider(sites)

    def choose_url(self) -> str:
        site = self._rng.choice(self._sites)
        return site.url

    def iter_urls_round_robin(self) -> Iterable[str]:
        while True:
            for site in self._sites:
                yield site.url


class URLListProvider:
    """Provider backed by an explicit list of URLs."""

    def __init__(self, urls: list[str], *, seed: int | None = None) -> None:
        if not urls:
            raise ValueError("urls list must be non-empty")
        self._urls = urls
        self._rng = Random(seed)

    def choose_url(self) -> str:
        return self._rng.choice(self._urls)


def build_fixture_urls(base_url: str, fixtures_dir: str) -> list[str]:
    """Enumerate fixture HTML URLs under fixtures_dir."""
    root = Path(fixtures_dir)
    if not root.exists():
        raise ValueError(f"fixtures_dir does not exist: {fixtures_dir}")

    urls: list[str] = []
    for path in root.rglob("*.html"):
        rel = path.relative_to(root).as_posix()
        urls.append(f"{base_url.rstrip('/')}/{rel}")

    # Prefer a stable order before random choice.
    urls.sort()
    return urls
