"""Tests for Consumer retry/back-off and error classification logic."""

from __future__ import annotations

import pytest

from simulator.core.consumer import (
    _backoff_delay,
    _classify_exception,
    _classify_http_error,
)


class TestClassifyHttpError:
    """Verify canonical error_type mapping for HTTP status codes."""

    @pytest.mark.parametrize(
        "status,expected",
        [
            (200, None),
            (201, None),
            (301, None),
            (304, None),
            (401, "auth_unauthorized"),
            (403, "auth_forbidden"),
            (404, "not_found"),
            (429, "rate_limited"),
            (400, "client_error"),
            (422, "client_error"),
            (500, "server_error"),
            (502, "server_error"),
            (503, "server_error"),
            (504, "server_error"),
        ],
    )
    def test_status_mapping(self, status: int, expected: str | None) -> None:
        assert _classify_http_error(status) == expected


class TestClassifyException:
    """Verify canonical error_type for common httpx exceptions."""

    def test_timeout(self) -> None:
        import httpx

        exc = httpx.ReadTimeout("timed out")
        assert _classify_exception(exc) == "network_timeout"

    def test_connect_error(self) -> None:
        import httpx

        exc = httpx.ConnectError("refused")
        assert _classify_exception(exc) == "network_connect"

    def test_generic_http_error(self) -> None:
        import httpx

        exc = httpx.DecodingError("bad encoding")
        assert _classify_exception(exc) == "network_error"

    def test_non_httpx_exception(self) -> None:
        exc = RuntimeError("oops")
        assert _classify_exception(exc) == "RuntimeError"


class TestBackoffDelay:
    """Verify exponential back-off with Retry-After support."""

    def test_exponential_growth(self) -> None:
        assert _backoff_delay(0, base=1.0, cap=30.0) == 1.0
        assert _backoff_delay(1, base=1.0, cap=30.0) == 2.0
        assert _backoff_delay(2, base=1.0, cap=30.0) == 4.0
        assert _backoff_delay(3, base=1.0, cap=30.0) == 8.0

    def test_cap_applied(self) -> None:
        assert _backoff_delay(10, base=1.0, cap=5.0) == 5.0

    def test_retry_after_header_honoured(self) -> None:
        delay = _backoff_delay(0, base=1.0, cap=30.0, retry_after="7")
        assert delay == 7.0

    def test_retry_after_capped(self) -> None:
        delay = _backoff_delay(0, base=1.0, cap=5.0, retry_after="20")
        assert delay == 5.0

    def test_retry_after_invalid_fallback(self) -> None:
        delay = _backoff_delay(2, base=1.0, cap=30.0, retry_after="not-a-number")
        assert delay == 4.0  # falls back to exponential
