"""Tests for the fixture storage module."""

from __future__ import annotations

import pytest

from simulator.fixtures.storage import (
    FileMeta,
    FixtureStore,
    RecordingMeta,
    SiteMeta,
    url_to_slug,
)


class TestUrlToSlug:
    """URL-to-slug conversion tests."""

    def test_simple_domain(self):
        assert url_to_slug("https://example.com") == "example_com"

    def test_domain_with_path(self):
        assert url_to_slug("https://www.scmp.com/business") == "www_scmp_com_business"

    def test_strips_trailing_slash(self):
        assert url_to_slug("https://example.com/") == "example_com"

    def test_strips_scheme(self):
        assert url_to_slug("http://example.com") == "example_com"

    def test_subdomain(self):
        assert url_to_slug("https://asia.nikkei.com") == "asia_nikkei_com"

    def test_collapses_special_chars(self):
        assert url_to_slug("https://example.com/a?b=c&d=e") == "example_com_a_b_c_d_e"

    def test_empty_yields_unknown(self):
        assert url_to_slug("") == "unknown"


class TestRecordingMeta:
    """Meta serialization tests."""

    def test_round_trip(self):
        meta = RecordingMeta(
            version=1,
            recorded_at="2026-02-17T00:00:00+00:00",
            sites=[
                SiteMeta(
                    slug="example_com",
                    original_url="https://example.com",
                    files=[
                        FileMeta(
                            path="index.html",
                            content_type="text/html",
                            original_status=200,
                            size_bytes=1234,
                            obfuscated=True,
                        )
                    ],
                )
            ],
        )
        data = meta.to_dict()
        restored = RecordingMeta.from_dict(data)
        assert restored.version == 1
        assert len(restored.sites) == 1
        assert restored.sites[0].slug == "example_com"
        assert restored.sites[0].files[0].size_bytes == 1234

    def test_empty_sites(self):
        meta = RecordingMeta(version=1, recorded_at="now", sites=[])
        data = meta.to_dict()
        restored = RecordingMeta.from_dict(data)
        assert restored.sites == []


class TestFixtureStore:
    """Fixture store filesystem tests."""

    def test_ensure_dirs_creates_directory(self, tmp_path):
        store = FixtureStore(tmp_path / "new_dir")
        store.ensure_dirs()
        assert store.data_dir.exists()

    def test_write_and_read_meta(self, tmp_path):
        store = FixtureStore(tmp_path)
        meta = RecordingMeta(
            version=1,
            recorded_at="2026-02-17T00:00:00+00:00",
            sites=[
                SiteMeta(slug="test", original_url="https://test.com", files=[])
            ],
        )
        store.write_meta(meta)
        assert store.meta_path.exists()

        loaded = store.load_meta()
        assert loaded.version == 1
        assert loaded.sites[0].slug == "test"

    def test_load_meta_missing_raises(self, tmp_path):
        store = FixtureStore(tmp_path)
        with pytest.raises(FileNotFoundError):
            store.load_meta()

    def test_write_file(self, tmp_path):
        store = FixtureStore(tmp_path)
        content = b"<html><body>Hello</body></html>"
        path = store.write_file("test_site", "index.html", content)
        assert path.exists()
        assert path.read_bytes() == content
        assert path.parent.name == "test_site"

    def test_list_html_files(self, tmp_path):
        store = FixtureStore(tmp_path)
        store.write_file("site_a", "index.html", b"<html>A</html>")
        store.write_file("site_b", "index.html", b"<html>B</html>")
        files = store.list_html_files()
        assert len(files) == 2
        names = {f.parent.name for f in files}
        assert names == {"site_a", "site_b"}

    def test_list_html_files_empty_dir(self, tmp_path):
        store = FixtureStore(tmp_path / "nonexistent")
        assert store.list_html_files() == []

    def test_site_dir_creates_subdirectory(self, tmp_path):
        store = FixtureStore(tmp_path)
        site_path = store.site_dir("my_site")
        assert site_path.exists()
        assert site_path.name == "my_site"
