"""Custom exceptions for group-aware registries and rendering pipeline.

All exceptions include detailed error messages designed for LLM processing,
enabling intelligent error recovery and decision-making.
"""

from app.exceptions.base import (
    GofrDigError,
    ValidationError,
    ResourceNotFoundError,
    SecurityError,
    ConfigurationError,
    RegistryError,
)
from app.exceptions.template import TemplateNotFoundError
from app.exceptions.fragment import FragmentNotFoundError
from app.exceptions.group import GroupMismatchError
from app.exceptions.style import StyleNotFoundError
from app.exceptions.invalid_group import InvalidGroupError
from app.exceptions.session import (
    SessionError,
    SessionNotFoundError,
    SessionValidationError,
    InvalidSessionStateError,
)

__all__ = [
    # Base exceptions
    "GofrDigError",
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
