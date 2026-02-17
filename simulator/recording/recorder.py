"""Recorder: fetches live sites and saves obfuscated HTML fixtures.

The ``Recorder`` class drives the recording session:
  1. Iterates through all sites in the provider.
  2. Fetches each URL via HTTP GET.
  3. Passes the response HTML through the obfuscator.
  4. Writes the result to the fixture store.
  5. Builds and writes ``meta.json``.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.logger import Logger, session_logger

from simulator.fixtures.storage import (
    FileMeta,
    FixtureStore,
    RecordingMeta,
    SiteMeta,
    url_to_slug,
)
from simulator.recording.obfuscator import obfuscate


@dataclass
class RecordResult:
    """Summary of a recording run."""

    sites_attempted: int = 0
    sites_recorded: int = 0
    sites_failed: int = 0
    total_bytes: int = 0


class Recorder:
    """Fetches live URLs and saves obfuscated fixtures.

    Usage::

        recorder = Recorder(
            store=FixtureStore("simulator/fixtures/data"),
            timeout_seconds=30.0,
        )
        result = await recorder.record_urls(["https://example.com", ...])
    """

    def __init__(
        self,
        *,
        store: FixtureStore,
        timeout_seconds: float = 30.0,
        logger: Logger | None = None,
    ) -> None:
        self._store = store
        self._timeout = timeout_seconds
        self._logger = logger or session_logger

    async def record_urls(self, urls: list[str]) -> RecordResult:
        """Fetch each URL, obfuscate, and save as a fixture.

        Returns a summary of the recording run.
        """
        self._store.ensure_dirs()
        result = RecordResult()
        meta = RecordingMeta(
            version=1,
            recorded_at=FixtureStore.now_iso(),
        )

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
            headers={
                "User-Agent": "gofr-dig-recorder/0.1",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        ) as client:
            for url in urls:
                result.sites_attempted += 1
                try:
                    site_meta = await self._record_one(client, url)
                    meta.sites.append(site_meta)
                    result.sites_recorded += 1
                    for f in site_meta.files:
                        result.total_bytes += f.size_bytes
                except Exception as exc:
                    result.sites_failed += 1
                    self._logger.warning(
                        "recorder.site_failed",
                        event="recorder.site_failed",
                        url=url,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )

        self._store.write_meta(meta)

        self._logger.info(
            "recorder.complete",
            event="recorder.complete",
            sites_attempted=result.sites_attempted,
            sites_recorded=result.sites_recorded,
            sites_failed=result.sites_failed,
            total_bytes=result.total_bytes,
            meta_path=str(self._store.meta_path),
        )

        return result

    async def _record_one(self, client: httpx.AsyncClient, url: str) -> SiteMeta:
        """Fetch, obfuscate, and store a single URL."""
        slug = url_to_slug(url)

        self._logger.info(
            "recorder.fetching",
            event="recorder.fetching",
            url=url,
            slug=slug,
        )

        response = await client.get(url)
        content_type = response.headers.get("content-type", "text/html")
        status = response.status_code

        raw_html = response.text
        obfuscated_html = obfuscate(raw_html)
        content_bytes = obfuscated_html.encode("utf-8")

        filename = "index.html"
        self._store.write_file(slug, filename, content_bytes)

        file_meta = FileMeta(
            path=filename,
            content_type=content_type,
            original_status=status,
            size_bytes=len(content_bytes),
            obfuscated=True,
        )

        self._logger.info(
            "recorder.site_saved",
            event="recorder.site_saved",
            url=url,
            slug=slug,
            status=status,
            size_bytes=len(content_bytes),
        )

        return SiteMeta(
            slug=slug,
            original_url=url,
            files=[file_meta],
        )
