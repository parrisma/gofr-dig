"""Tests for SSRF URL validation."""

from unittest.mock import patch

from app.scraping.url_validator import validate_url


def test_blocks_private_ipv4_when_not_bypassed(monkeypatch):
    """Private RFC1918 targets should be blocked."""
    monkeypatch.delenv("GOFR_DIG_ALLOW_PRIVATE_URLS", raising=False)

    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.1.2.3", 0))]):
        is_safe, reason = validate_url("http://internal.example")

    assert is_safe is False
    assert "private/internal" in reason


def test_blocks_metadata_hostnames(monkeypatch):
    """Known cloud metadata hostnames should be blocked."""
    monkeypatch.delenv("GOFR_DIG_ALLOW_PRIVATE_URLS", raising=False)

    is_safe, reason = validate_url("http://metadata.google.internal")

    assert is_safe is False
    assert "blocked" in reason.lower()


def test_allows_when_bypass_enabled(monkeypatch):
    """Test bypass env var for controlled test environments."""
    monkeypatch.setenv("GOFR_DIG_ALLOW_PRIVATE_URLS", "true")

    is_safe, reason = validate_url("http://10.0.0.2")

    assert is_safe is True
    assert reason == ""
