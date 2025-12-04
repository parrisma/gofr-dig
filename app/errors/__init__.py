"""Error handling utilities for GOFR-DIG."""

from app.errors.mapper import (
    map_exception_to_response,
    map_error_for_mcp,
    map_error_for_web,
    get_http_status_for_error,
    get_recovery_strategy,
)

__all__ = [
    "map_exception_to_response",
    "map_error_for_mcp",
    "map_error_for_web",
    "get_http_status_for_error",
    "get_recovery_strategy",
]
