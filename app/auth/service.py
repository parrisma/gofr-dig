"""JWT Authentication Service

Handles JWT token creation, validation, and group mapping.
"""

import jwt
import os
from datetime import datetime, timedelta
from typing import Optional, Dict
from pathlib import Path
import json
from pydantic import BaseModel
from app.config import get_default_token_store_path
from app.logger import Logger, session_logger


class TokenInfo(BaseModel):
    """Information extracted from a JWT token"""

    token: str
    group: str
    expires_at: datetime
    issued_at: datetime


class AuthService:
    """Service for JWT authentication and group management"""

    def __init__(self, secret_key: Optional[str] = None, token_store_path: Optional[str] = None):
        """
        Initialize the authentication service

        Args:
            secret_key: Secret key for JWT signing (defaults to env var or generates one)
            token_store_path: Path to store token-group mappings. If None, uses configured default from app.config
        """
        self.logger: Logger = session_logger

        # Get or create secret key
        secret = secret_key or os.environ.get("GOFR_DIG_JWT_SECRET")
        if not secret:
            self.logger.warning(
                "No JWT secret provided, generating random secret (not suitable for production)"
            )
            secret = os.urandom(32).hex()
        self.secret_key: str = secret

        # Setup token store
        if token_store_path is None:
            token_store_path = get_default_token_store_path()
        self.token_store_path = Path(token_store_path)
        self._load_token_store()

        self.logger.info("AuthService initialized", token_store=str(self.token_store_path))

    def _load_token_store(self) -> None:
        """Load token-group mappings from disk"""
        if self.token_store_path.exists():
            try:
                with open(self.token_store_path, "r") as f:
                    self.token_store = json.load(f)
                self.logger.debug(
                    "Token store loaded from disk",
                    tokens_count=len(self.token_store),
                    path=str(self.token_store_path),
                )
            except Exception as e:
                self.logger.error("Failed to load token store", error=str(e))
                self.token_store = {}
        else:
            self.token_store = {}
            self.logger.debug("Token store initialized as empty", path=str(self.token_store_path))

    def _save_token_store(self) -> None:
        """Save token-group mappings to disk"""
        try:
            self.token_store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_store_path, "w") as f:
                json.dump(self.token_store, f, indent=2)
            self.logger.debug("Token store saved", tokens_count=len(self.token_store))
        except Exception as e:
            self.logger.error("Failed to save token store", error=str(e))
            raise

    def create_token(self, group: str, expires_in_seconds: int = 2592000) -> str:
        """
        Create a new JWT token for a group

        Args:
            group: The group name to associate with this token
            expires_in_seconds: Number of seconds until token expires (default: 2592000 = 30 days)

        Returns:
            JWT token string
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=expires_in_seconds)

        payload = {
            "group": group,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }

        token = jwt.encode(payload, self.secret_key, algorithm="HS256")

        # Store token-group mapping
        self.token_store[token] = {
            "group": group,
            "issued_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        self._save_token_store()

        self.logger.info(
            "Token created",
            group=group,
            expires_at=expires_at.isoformat(),
            expires_in_seconds=expires_in_seconds,
        )

        return token

    def verify_token(self, token: str) -> TokenInfo:
        """
        Verify a JWT token and extract information

        Args:
            token: JWT token string

        Returns:
            TokenInfo with group and expiry information

        Raises:
            ValueError: If token is invalid or expired
        """
        try:
            # Reload token store to get latest tokens created by admin
            self._load_token_store()

            # Decode and verify token
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])

            group = payload.get("group")
            if not group:
                self.logger.error("Token missing group claim")
                raise ValueError("Token missing group claim")

            # Check if token is in our store (REQUIRED - admin must pre-create tokens)
            if token not in self.token_store:
                self.logger.warning("Token not found in store", group=group)
                raise ValueError("Token not found in token store. Tokens must be created by admin.")

            issued_at = datetime.fromtimestamp(payload["iat"])
            expires_at = datetime.fromtimestamp(payload["exp"])

            self.logger.debug("Token verified", group=group, expires_at=expires_at.isoformat())

            return TokenInfo(token=token, group=group, expires_at=expires_at, issued_at=issued_at)

        except jwt.ExpiredSignatureError:
            self.logger.warning("Token expired")
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            self.logger.error("Invalid token", error=str(e))
            raise ValueError(f"Invalid token: {str(e)}")

    def revoke_token(self, token: str) -> None:
        """
        Revoke a token by removing it from the store

        Args:
            token: JWT token string to revoke
        """
        # Reload to get latest state
        self._load_token_store()

        if token in self.token_store:
            group = self.token_store[token]["group"]
            del self.token_store[token]
            self._save_token_store()
            self.logger.info("Token revoked", group=group)
        else:
            self.logger.warning("Token not found for revocation")

    def list_tokens(self) -> Dict[str, Dict]:
        """
        List all tokens in the store

        Returns:
            Dictionary of token -> token info
        """
        # Reload to get latest state from shared store
        self._load_token_store()
        return self.token_store.copy()

    def get_group_for_token(self, token: str) -> str:
        """
        Get the group associated with a token

        Args:
            token: JWT token string

        Returns:
            Group name

        Raises:
            ValueError: If token is invalid
        """
        token_info = self.verify_token(token)
        return token_info.group
