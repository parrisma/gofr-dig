"""Fixture storage layout and metadata management.

Directory structure produced by the recorder::

    simulator/fixtures/data/
    ├── meta.json               # recording metadata (list of sites + files)
    ├── asia_nikkei_com/
    │   └── index.html          # obfuscated HTML
    ├── www_scmp_com_business/
    │   └── index.html
    └── ...
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class FileMeta:
    """Metadata for a single recorded file."""

    path: str
    content_type: str
    original_status: int
    size_bytes: int = 0
    obfuscated: bool = True


@dataclass
class SiteMeta:
    """Metadata for one recorded site."""

    slug: str
    original_url: str
    files: list[FileMeta] = field(default_factory=list)


@dataclass
class RecordingMeta:
    """Top-level metadata for a recording session."""

    version: int = 1
    recorded_at: str = ""
    sites: list[SiteMeta] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "RecordingMeta":
        sites = []
        for site_raw in data.get("sites", []):
            files = [FileMeta(**f) for f in site_raw.get("files", [])]
            sites.append(
                SiteMeta(
                    slug=site_raw["slug"],
                    original_url=site_raw["original_url"],
                    files=files,
                )
            )
        return RecordingMeta(
            version=data.get("version", 1),
            recorded_at=data.get("recorded_at", ""),
            sites=sites,
        )


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def url_to_slug(url: str) -> str:
    """Convert a URL to a filesystem-safe slug.

    Examples:
        https://asia.nikkei.com       -> asia_nikkei_com
        https://www.scmp.com/business -> www_scmp_com_business
    """
    # Strip scheme
    cleaned = re.sub(r"^https?://", "", url)
    # Remove trailing slash
    cleaned = cleaned.rstrip("/")
    # Replace non-alpha with underscore, collapse runs
    slug = _SLUG_RE.sub("_", cleaned.lower()).strip("_")
    return slug or "unknown"


class FixtureStore:
    """Manages the fixture data directory layout."""

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def meta_path(self) -> Path:
        return self._data_dir / "meta.json"

    def ensure_dirs(self) -> None:
        """Create the data directory if it does not exist."""
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def site_dir(self, slug: str) -> Path:
        """Return (and create) the directory for a specific site."""
        path = self._data_dir / slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_file(self, slug: str, filename: str, content: bytes) -> Path:
        """Write a recorded file to disk and return its path."""
        site_path = self.site_dir(slug)
        file_path = site_path / filename
        file_path.write_bytes(content)
        return file_path

    def write_meta(self, meta: RecordingMeta) -> None:
        """Write meta.json to disk."""
        self.ensure_dirs()
        self.meta_path.write_text(
            json.dumps(meta.to_dict(), indent=2, sort_keys=False),
            encoding="utf-8",
        )

    def load_meta(self) -> RecordingMeta:
        """Load meta.json from disk."""
        if not self.meta_path.exists():
            raise FileNotFoundError(f"meta.json not found: {self.meta_path}")
        data = json.loads(self.meta_path.read_text(encoding="utf-8"))
        return RecordingMeta.from_dict(data)

    def list_html_files(self) -> list[Path]:
        """List all HTML files under the data directory."""
        if not self._data_dir.exists():
            return []
        files = sorted(self._data_dir.rglob("*.html"))
        return files

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
