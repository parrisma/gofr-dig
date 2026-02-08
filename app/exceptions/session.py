"""Session-specific exceptions for GOFR-DIG.

These exceptions provide typed, structured errors for session operations,
enabling proper error classification in both MCP and web interfaces.
"""

from gofr_common.exceptions import GofrError, ResourceNotFoundError, ValidationError


class SessionError(GofrError):
    """Base exception for session-related errors."""

    pass


class SessionNotFoundError(ResourceNotFoundError):
    """Raised when a session ID does not exist in storage."""

    pass


class SessionValidationError(ValidationError):
    """Raised when session arguments are invalid (e.g., chunk index out of range)."""

    pass


class InvalidSessionStateError(ValidationError):
    """Raised when a session is in an unexpected state."""

    pass
