"""Custom exceptions for group-aware registries and rendering pipeline.

All exceptions include detailed error messages designed for LLM processing,
enabling intelligent error recovery and decision-making.

Base exceptions are re-exported from gofr_common.exceptions.
"""

# Re-export common exceptions from gofr_common
from gofr_common.exceptions import (
    GofrError,
    ValidationError,
    ResourceNotFoundError,
    SecurityError,
    ConfigurationError,
    RegistryError,
)

# Project-specific alias for backward compatibility
GofrDigError = GofrError

# Optional imports for modules that may not exist yet
try:
    from app.exceptions.template import TemplateNotFoundError  # type: ignore[import-not-found]
except ImportError:
    TemplateNotFoundError = type("TemplateNotFoundError", (ResourceNotFoundError,), {})  # type: ignore[misc, assignment]

try:
    from app.exceptions.fragment import FragmentNotFoundError  # type: ignore[import-not-found]
except ImportError:
    FragmentNotFoundError = type("FragmentNotFoundError", (ResourceNotFoundError,), {})  # type: ignore[misc, assignment]

try:
    from app.exceptions.group import GroupMismatchError  # type: ignore[import-not-found]
except ImportError:
    GroupMismatchError = type("GroupMismatchError", (SecurityError,), {})  # type: ignore[misc, assignment]

try:
    from app.exceptions.style import StyleNotFoundError  # type: ignore[import-not-found]
except ImportError:
    StyleNotFoundError = type("StyleNotFoundError", (ResourceNotFoundError,), {})  # type: ignore[misc, assignment]

try:
    from app.exceptions.invalid_group import InvalidGroupError  # type: ignore[import-not-found]
except ImportError:
    InvalidGroupError = type("InvalidGroupError", (ValidationError,), {})  # type: ignore[misc, assignment]

try:
    from app.exceptions.session import (  # type: ignore[import-not-found]
        SessionError,
        SessionNotFoundError,
        SessionValidationError,
        InvalidSessionStateError,
    )
except ImportError:
    SessionError = type("SessionError", (GofrError,), {})  # type: ignore[misc, assignment]
    SessionNotFoundError = type("SessionNotFoundError", (ResourceNotFoundError,), {})  # type: ignore[misc, assignment]
    SessionValidationError = type("SessionValidationError", (ValidationError,), {})  # type: ignore[misc, assignment]
    InvalidSessionStateError = type("InvalidSessionStateError", (ValidationError,), {})  # type: ignore[misc, assignment]

__all__ = [
    # Base exceptions (from gofr_common)
    "GofrError",
    "GofrDigError",  # Alias for backward compatibility
    "ValidationError",
    "ResourceNotFoundError",
    "SecurityError",
    "ConfigurationError",
    "RegistryError",
    # Specific exceptions
    "TemplateNotFoundError",
    "FragmentNotFoundError",
    "GroupMismatchError",
    "StyleNotFoundError",
    "InvalidGroupError",
    "SessionError",
    "SessionNotFoundError",
    "SessionValidationError",
    "InvalidSessionStateError",
]

