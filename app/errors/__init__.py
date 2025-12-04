"""Error handling utilities for GOFR-DIG."""

from app.errors.mapper import (
    create_error_response,
    error_to_mcp_response,
    error_to_web_response,
    get_error_code,
    get_recovery_strategy,
)

__all__ = [
    "create_error_response",
    "error_to_mcp_response",
    "error_to_web_response",
    "get_error_code",
    "get_recovery_strategy",
]
