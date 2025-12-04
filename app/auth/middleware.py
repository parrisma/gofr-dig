"""Authentication middleware

Provides utilities for validating JWT tokens in web requests.
"""

from typing import Optional
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth.service import AuthService, TokenInfo
from app.logger import session_logger as logger

# Global auth service instance
_auth_service: Optional[AuthService] = None

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


def init_auth_service(
    secret_key: Optional[str] = None, token_store_path: Optional[str] = None
) -> AuthService:
    """
    Initialize the global auth service

    Args:
        secret_key: JWT secret key
        token_store_path: Path to token store

    Returns:
        AuthService instance
    """
    global _auth_service
    _auth_service = AuthService(secret_key=secret_key, token_store_path=token_store_path)
    logger.info("Auth service initialized", token_store=token_store_path)
    return _auth_service


def get_auth_service() -> AuthService:
    """
    Get the global auth service instance

    Returns:
        AuthService instance

    Raises:
        RuntimeError: If auth service not initialized
    """
    if _auth_service is None:
        raise RuntimeError("AuthService not initialized. Call init_auth_service() first.")
    return _auth_service


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> TokenInfo:
    """
    Verify JWT token from request

    Args:
        credentials: HTTP authorization credentials

    Returns:
        TokenInfo with group and expiry information

    Raises:
        HTTPException: If token is invalid or missing
    """
    try:
        auth_service = get_auth_service()
        token_info = auth_service.verify_token(credentials.credentials)
        logger.debug("Token verified", group=token_info.group)
        return token_info
    except ValueError as e:
        logger.warning("Token verification failed", error=str(e))
        raise HTTPException(status_code=401, detail=str(e))
    except RuntimeError as e:
        logger.error("Auth service error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


def optional_verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(optional_security),
) -> Optional[TokenInfo]:
    """
    Optionally verify JWT token from request (doesn't require authentication)

    Args:
        credentials: HTTP authorization credentials (optional)

    Returns:
        TokenInfo if token provided and valid, None if no token provided

    Raises:
        HTTPException: If token is provided but invalid
    """
    if credentials is None:
        # No token provided, return None (anonymous access)
        logger.debug("Anonymous access - no token provided")
        return None

    try:
        auth_service = get_auth_service()
        token_info = auth_service.verify_token(credentials.credentials)
        logger.debug("Optional token verified", group=token_info.group)
        return token_info
    except ValueError as e:
        logger.warning("Optional token verification failed", error=str(e))
        raise HTTPException(status_code=401, detail=str(e))
    except RuntimeError:
        # Auth service not initialized - allow anonymous access
        logger.debug("Auth service not initialized - allowing anonymous access")
        return None
