"""Tests for auth middleware.

Phase 11: Tests for authentication middleware functions.

These tests verify:
1. init_auth_service initializes global service
2. get_auth_service returns initialized service
3. verify_token validates tokens correctly
4. optional_verify_token handles missing tokens
"""

import pytest

from app.auth.middleware import (
    init_auth_service,
    get_auth_service,
    verify_token,
    optional_verify_token,
)
from app.auth.service import AuthService


class TestInitAuthService:
    """Tests for init_auth_service function."""

    def test_creates_auth_service(self, tmp_path):
        """Test init_auth_service creates an AuthService."""
        token_store = str(tmp_path / "tokens.json")
        service = init_auth_service(
            secret_key="test-secret",
            token_store_path=token_store,
        )

        assert service is not None
        assert isinstance(service, AuthService)

    def test_sets_global_service(self, tmp_path):
        """Test init_auth_service sets the global _auth_service."""
        from app.auth import middleware

        token_store = str(tmp_path / "tokens.json")
        service = init_auth_service(
            secret_key="test-secret",
            token_store_path=token_store,
        )

        assert middleware._auth_service is service


class TestGetAuthService:
    """Tests for get_auth_service function."""

    def test_returns_initialized_service(self, tmp_path):
        """Test get_auth_service returns the initialized service."""
        from app.auth import middleware

        token_store = str(tmp_path / "tokens.json")
        init_auth_service(
            secret_key="test-secret",
            token_store_path=token_store,
        )

        service = get_auth_service()
        assert service is middleware._auth_service

    def test_raises_if_not_initialized(self):
        """Test get_auth_service raises if not initialized."""
        from app.auth import middleware

        # Clear the global service
        original = middleware._auth_service
        middleware._auth_service = None

        try:
            with pytest.raises(RuntimeError) as exc_info:
                get_auth_service()

            assert "not initialized" in str(exc_info.value).lower()
        finally:
            # Restore original
            middleware._auth_service = original


class TestVerifyToken:
    """Tests for verify_token function."""

    def test_valid_token_returns_token_info(self, tmp_path):
        """Test verify_token returns TokenInfo for valid token."""
        from fastapi.security import HTTPAuthorizationCredentials

        token_store = str(tmp_path / "tokens.json")
        service = init_auth_service(
            secret_key="test-secret",
            token_store_path=token_store,
        )

        # Create a token
        token = service.create_token(group="test_group")

        # Mock credentials
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token,
        )

        # Verify
        token_info = verify_token(credentials)

        assert token_info is not None
        assert token_info.group == "test_group"

    def test_invalid_token_raises_401(self, tmp_path):
        """Test verify_token raises HTTPException 401 for invalid token."""
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        token_store = str(tmp_path / "tokens.json")
        init_auth_service(
            secret_key="test-secret",
            token_store_path=token_store,
        )

        # Mock credentials with invalid token
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid-token",
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_token(credentials)

        assert exc_info.value.status_code == 401


class TestOptionalVerifyToken:
    """Tests for optional_verify_token function."""

    def test_returns_none_for_missing_token(self, tmp_path):
        """Test optional_verify_token returns None when no token provided."""
        token_store = str(tmp_path / "tokens.json")
        init_auth_service(
            secret_key="test-secret",
            token_store_path=token_store,
        )

        result = optional_verify_token(None)
        assert result is None

    def test_returns_token_info_for_valid_token(self, tmp_path):
        """Test optional_verify_token returns TokenInfo for valid token."""
        from fastapi.security import HTTPAuthorizationCredentials

        token_store = str(tmp_path / "tokens.json")
        service = init_auth_service(
            secret_key="test-secret",
            token_store_path=token_store,
        )

        # Create a token
        token = service.create_token(group="test_group")

        # Mock credentials
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token,
        )

        # Verify
        token_info = optional_verify_token(credentials)

        assert token_info is not None
        assert token_info.group == "test_group"

    def test_raises_401_for_invalid_token(self, tmp_path):
        """Test optional_verify_token raises 401 for invalid token."""
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        token_store = str(tmp_path / "tokens.json")
        init_auth_service(
            secret_key="test-secret",
            token_store_path=token_store,
        )

        # Mock credentials with invalid token
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid-token",
        )

        with pytest.raises(HTTPException) as exc_info:
            optional_verify_token(credentials)

        assert exc_info.value.status_code == 401

    def test_returns_none_when_service_not_initialized(self):
        """Test optional_verify_token returns None when service not initialized."""
        from app.auth import middleware
        from fastapi.security import HTTPAuthorizationCredentials

        # Clear the global service
        original = middleware._auth_service
        middleware._auth_service = None

        try:
            # Should return None, not raise
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="some-token",
            )
            result = optional_verify_token(credentials)
            assert result is None
        finally:
            # Restore original
            middleware._auth_service = original
