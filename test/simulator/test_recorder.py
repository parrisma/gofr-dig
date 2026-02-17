"""Tests for the recorder module."""

from __future__ import annotations

import httpx
import pytest

from simulator.fixtures.storage import FixtureStore
from simulator.recording.recorder import Recorder


@pytest.fixture
def fixture_store(tmp_path):
    """Create an empty fixture store in a temp directory."""
    return FixtureStore(tmp_path / "fixtures")


class TestRecorder:
    """Recorder integration tests using httpx mocking."""

    @pytest.mark.asyncio
    async def test_records_single_url(self, fixture_store):
        """Record a single URL and verify output."""
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text="<html><body><h1>Test Headline</h1><p>Email: user@test.com</p></body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            )
        )
        recorder = Recorder(store=fixture_store, timeout_seconds=5.0)
        # Patch the client to use mock transport
        result = await _record_with_transport(recorder, ["https://example.com"], transport)

        assert result.sites_attempted == 1
        assert result.sites_recorded == 1
        assert result.sites_failed == 0
        assert result.total_bytes > 0

        # meta.json should exist
        meta = fixture_store.load_meta()
        assert len(meta.sites) == 1
        assert meta.sites[0].slug == "example_com"
        assert meta.sites[0].original_url == "https://example.com"

        # Obfuscated file should exist
        html_files = fixture_store.list_html_files()
        assert len(html_files) == 1
        content = html_files[0].read_text(encoding="utf-8")

        # Original text should be gone
        assert "Test Headline" not in content
        assert "user@test.com" not in content

        # Structure should be preserved
        assert "<h1>" in content
        assert "</h1>" in content
        assert "<body>" in content

    @pytest.mark.asyncio
    async def test_records_multiple_urls(self, fixture_store):
        """Record multiple URLs."""
        responses = {
            "https://site-a.com": "<html><body><p>Site A content</p></body></html>",
            "https://site-b.com": "<html><body><p>Site B content</p></body></html>",
        }

        def handler(request):
            body = responses.get(str(request.url), "<html><body>Default</body></html>")
            return httpx.Response(200, text=body, headers={"content-type": "text/html"})

        transport = httpx.MockTransport(handler)
        recorder = Recorder(store=fixture_store, timeout_seconds=5.0)
        result = await _record_with_transport(
            recorder,
            ["https://site-a.com", "https://site-b.com"],
            transport,
        )

        assert result.sites_recorded == 2
        meta = fixture_store.load_meta()
        slugs = {s.slug for s in meta.sites}
        assert "site_a_com" in slugs
        assert "site_b_com" in slugs

    @pytest.mark.asyncio
    async def test_handles_fetch_failure(self, fixture_store):
        """Failed fetches are counted but don't stop the run."""

        def handler(request):
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handler)
        recorder = Recorder(store=fixture_store, timeout_seconds=5.0)
        result = await _record_with_transport(recorder, ["https://fail.example.com"], transport)

        assert result.sites_attempted == 1
        assert result.sites_recorded == 0
        assert result.sites_failed == 1

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self, fixture_store):
        """Mix of successful and failed URLs."""
        call_count = 0

        def handler(request):
            nonlocal call_count
            call_count += 1
            if "fail" in str(request.url):
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, text="<html><body>OK</body></html>", headers={"content-type": "text/html"})

        transport = httpx.MockTransport(handler)
        recorder = Recorder(store=fixture_store, timeout_seconds=5.0)
        result = await _record_with_transport(
            recorder,
            ["https://good.com", "https://fail.com"],
            transport,
        )

        assert result.sites_attempted == 2
        assert result.sites_recorded == 1
        assert result.sites_failed == 1


async def _record_with_transport(recorder: Recorder, urls: list[str], transport: httpx.MockTransport):
    """Helper: run recorder with a mock transport instead of real HTTP."""
    async with httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(recorder._timeout),
        follow_redirects=True,
        headers={
            "User-Agent": "gofr-dig-recorder/0.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ) as client:
        recorder._store.ensure_dirs()
        from simulator.fixtures.storage import RecordingMeta
        from simulator.recording.recorder import RecordResult

        result = RecordResult()
        meta = RecordingMeta(
            version=1,
            recorded_at=recorder._store.now_iso(),
        )

        for url in urls:
            result.sites_attempted += 1
            try:
                site_meta = await recorder._record_one(client, url)
                meta.sites.append(site_meta)
                result.sites_recorded += 1
                for f in site_meta.files:
                    result.total_bytes += f.size_bytes
            except Exception:
                result.sites_failed += 1

        recorder._store.write_meta(meta)
        return result
