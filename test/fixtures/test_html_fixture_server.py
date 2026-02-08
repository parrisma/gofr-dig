"""Tests for HTML fixture server

Verifies the test fixture server is working correctly before
using it for scraping tool tests.
"""

import urllib.error
import urllib.request

import pytest


class TestHTMLFixtureServer:
    """Tests for the HTML fixture server."""

    def test_server_starts_and_serves_index(self, html_fixture_server):
        """Test that server starts and serves index.html."""
        url = html_fixture_server.get_url("index.html")
        
        with urllib.request.urlopen(url, timeout=5) as response:
            content = response.read().decode("utf-8")
            
        assert response.status == 200
        assert "ACME Corporation" in content
        assert "<nav" in content

    def test_server_serves_products_page(self, html_fixture_server):
        """Test that server serves products.html."""
        url = html_fixture_server.get_url("products.html")
        
        with urllib.request.urlopen(url, timeout=5) as response:
            content = response.read().decode("utf-8")
            
        assert response.status == 200
        assert "Widget Pro 3000" in content
        assert "Gadget Plus" in content

    def test_server_serves_chinese_page(self, html_fixture_server):
        """Test that server serves Chinese content correctly."""
        url = html_fixture_server.get_url("chinese.html")
        
        with urllib.request.urlopen(url, timeout=5) as response:
            content = response.read().decode("utf-8")
            
        assert response.status == 200
        assert "欢迎访问" in content
        assert "ACME公司" in content

    def test_server_serves_japanese_page(self, html_fixture_server):
        """Test that server serves Japanese content correctly."""
        url = html_fixture_server.get_url("japanese.html")
        
        with urllib.request.urlopen(url, timeout=5) as response:
            content = response.read().decode("utf-8")
            
        assert response.status == 200
        assert "ようこそ" in content
        assert "製品" in content

    def test_server_serves_blog_subdirectory(self, html_fixture_server):
        """Test that server serves files from subdirectories."""
        url = html_fixture_server.get_url("blog/index.html")
        
        with urllib.request.urlopen(url, timeout=5) as response:
            content = response.read().decode("utf-8")
            
        assert response.status == 200
        assert "ACME Blog" in content

    def test_server_serves_robots_txt(self, html_fixture_server):
        """Test that server serves robots.txt."""
        url = html_fixture_server.get_url("robots.txt")
        
        with urllib.request.urlopen(url, timeout=5) as response:
            content = response.read().decode("utf-8")
            
        assert response.status == 200
        assert "User-agent:" in content
        assert "Disallow:" in content

    def test_base_url_property(self, html_fixture_server):
        """Test that base_url property returns correct URL."""
        ext_host = html_fixture_server._external_host
        assert html_fixture_server.base_url == f"http://{ext_host}:8766"

    def test_get_url_strips_leading_slash(self, html_fixture_server):
        """Test that get_url handles leading slash correctly."""
        url1 = html_fixture_server.get_url("index.html")
        url2 = html_fixture_server.get_url("/index.html")
        
        assert url1 == url2
        ext_host = html_fixture_server._external_host
        assert url1 == f"http://{ext_host}:8766/index.html"

    def test_404_for_nonexistent_file(self, html_fixture_server):
        """Test that server returns 404 for non-existent files."""
        url = html_fixture_server.get_url("nonexistent.html")
        
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(url, timeout=5)
            
        assert exc_info.value.code == 404
