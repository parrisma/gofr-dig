"""Authentication configuration utilities for GOFR-DIG server."""

import os
from typing import Optional, Tuple
from app.config import Config
from app.logger import Logger


def resolve_auth_config(
    jwt_secret_arg: Optional[str],
    token_store_arg: Optional[str],
    require_auth: bool,
    logger: Logger,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve authentication configuration from arguments and environment.

    Priority order:
    1. Command line arguments
    2. Environment variables
    3. Auto-generation (for JWT secret only)

    Args:
        jwt_secret_arg: JWT secret from command line (--jwt-secret)
        token_store_arg: Token store path from command line (--token-store)
        require_auth: Whether authentication is required
        logger: Logger instance for reporting

    Returns:
        Tuple of (jwt_secret, token_store_path), both None if auth disabled
    """
    if not require_auth:
        logger.warning("Authentication disabled via --no-auth flag")
        return None, None

    # Resolve JWT secret
    jwt_secret = jwt_secret_arg or os.environ.get("GOFR_DIG_JWT_SECRET")
    if not jwt_secret:
        # Auto-generate a secret for development
        import secrets
        jwt_secret = secrets.token_hex(32)
        logger.warning(
            "No JWT secret provided, auto-generated one for this session",
            hint="Set GOFR_DIG_JWT_SECRET environment variable for persistent tokens",
        )

    # Resolve token store path
    token_store_path = token_store_arg or os.environ.get("GOFR_DIG_TOKEN_STORE")
    if not token_store_path:
        # Default to auth directory
        token_store_path = str(Config.get_auth_dir() / "tokens.json")
        logger.info(
            "Using default token store path",
            path=token_store_path,
        )

    return jwt_secret, token_store_path
