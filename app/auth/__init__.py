"""Authentication module

Provides JWT-based authentication with group mapping.
Re-exports from gofr_common.auth for backward compatibility.
"""

# Re-export everything from gofr_common.auth
from gofr_common.auth import (
    AuthService,
    TokenInfo,
    get_auth_service,
    verify_token,
    optional_verify_token,
    init_auth_service,
)

__all__ = [
    "AuthService",
    "TokenInfo",
    "get_auth_service",
    "verify_token",
    "optional_verify_token",
    "init_auth_service",
]
