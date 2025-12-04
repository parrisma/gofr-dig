"""Tests for custom exception hierarchy.

Phase 9: Tests for GofrDigError and subclasses.

These tests verify:
1. Exception structure (code, message, details)
2. Inheritance hierarchy
3. String representation
4. Details handling
"""

import pytest

from app.exceptions import (
    GofrDigError,
    ValidationError,
    ResourceNotFoundError,
    SecurityError,
    ConfigurationError,
    RegistryError,
)


class TestGofrDigError:
    """Tests for base GofrDigError class."""

    def test_basic_construction(self):
        """Test basic exception construction."""
        error = GofrDigError("TEST_CODE", "Test message")

        assert error.code == "TEST_CODE"
        assert error.message == "Test message"
        assert error.details == {}

    def test_construction_with_details(self):
        """Test exception with details dict."""
        details = {"key1": "value1", "key2": 42}
        error = GofrDigError("TEST_CODE", "Test message", details=details)

        assert error.details == details
        assert error.details["key1"] == "value1"
        assert error.details["key2"] == 42

    def test_str_without_details(self):
        """Test string representation without details."""
        error = GofrDigError("TEST_CODE", "Test message")

        assert str(error) == "TEST_CODE: Test message"

    def test_str_with_details(self):
        """Test string representation with details."""
        error = GofrDigError("TEST_CODE", "Test message", details={"foo": "bar"})

        result = str(error)
        assert "TEST_CODE" in result
        assert "Test message" in result
        assert "foo" in result
        assert "bar" in result

    def test_is_exception(self):
        """Test that GofrDigError is an Exception."""
        error = GofrDigError("TEST", "test")
        assert isinstance(error, Exception)

    def test_can_be_raised(self):
        """Test that exception can be raised and caught."""
        with pytest.raises(GofrDigError) as exc_info:
            raise GofrDigError("RAISED", "This was raised")

        assert exc_info.value.code == "RAISED"
        assert exc_info.value.message == "This was raised"


class TestValidationError:
    """Tests for ValidationError class."""

    def test_inherits_from_gofr_dig_error(self):
        """Test ValidationError inherits from GofrDigError."""
        error = ValidationError("CODE", "message")
        assert isinstance(error, GofrDigError)

    def test_inherits_from_exception(self):
        """Test ValidationError is an Exception."""
        error = ValidationError("CODE", "message")
        assert isinstance(error, Exception)

    def test_can_be_caught_as_base(self):
        """Test ValidationError can be caught as GofrDigError."""
        with pytest.raises(GofrDigError):
            raise ValidationError("VAL", "validation failed")

    def test_has_all_attributes(self):
        """Test ValidationError has code, message, details."""
        error = ValidationError("INVALID_INPUT", "Input is invalid", {"field": "url"})

        assert error.code == "INVALID_INPUT"
        assert error.message == "Input is invalid"
        assert error.details["field"] == "url"


class TestResourceNotFoundError:
    """Tests for ResourceNotFoundError class."""

    def test_inherits_from_gofr_dig_error(self):
        """Test ResourceNotFoundError inherits from GofrDigError."""
        error = ResourceNotFoundError("CODE", "message")
        assert isinstance(error, GofrDigError)

    def test_can_be_caught_specifically(self):
        """Test ResourceNotFoundError can be caught specifically."""
        with pytest.raises(ResourceNotFoundError):
            raise ResourceNotFoundError("NOT_FOUND", "Resource missing")

    def test_not_caught_as_validation_error(self):
        """Test ResourceNotFoundError is not caught as ValidationError."""
        with pytest.raises(ResourceNotFoundError):
            try:
                raise ResourceNotFoundError("NOT_FOUND", "Resource missing")
            except ValidationError:
                pytest.fail("Should not catch as ValidationError")
                raise


class TestSecurityError:
    """Tests for SecurityError class."""

    def test_inherits_from_gofr_dig_error(self):
        """Test SecurityError inherits from GofrDigError."""
        error = SecurityError("CODE", "message")
        assert isinstance(error, GofrDigError)

    def test_can_store_auth_details(self):
        """Test SecurityError can store authentication details."""
        error = SecurityError(
            "AUTH_FAILED",
            "Authentication failed",
            details={"reason": "invalid_token", "expired": True},
        )

        assert error.details["reason"] == "invalid_token"
        assert error.details["expired"] is True


class TestConfigurationError:
    """Tests for ConfigurationError class."""

    def test_inherits_from_gofr_dig_error(self):
        """Test ConfigurationError inherits from GofrDigError."""
        error = ConfigurationError("CODE", "message")
        assert isinstance(error, GofrDigError)

    def test_can_store_config_details(self):
        """Test ConfigurationError can store config details."""
        error = ConfigurationError(
            "MISSING_CONFIG",
            "Required configuration missing",
            details={"config_key": "API_KEY", "required": True},
        )

        assert error.details["config_key"] == "API_KEY"


class TestRegistryError:
    """Tests for RegistryError class."""

    def test_inherits_from_gofr_dig_error(self):
        """Test RegistryError inherits from GofrDigError."""
        error = RegistryError("Registry operation failed")
        assert isinstance(error, GofrDigError)

    def test_default_code(self):
        """Test RegistryError has default code."""
        error = RegistryError("Registry operation failed")
        assert error.code == "REGISTRY_ERROR"

    def test_custom_code(self):
        """Test RegistryError can have custom code."""
        error = RegistryError("message", code="CUSTOM_CODE")
        assert error.code == "CUSTOM_CODE"

    def test_backward_compatible_signature(self):
        """Test RegistryError has backward compatible signature (message first)."""
        error = RegistryError("The error message")
        assert error.message == "The error message"


class TestExceptionHierarchy:
    """Tests for overall exception hierarchy relationships."""

    def test_all_errors_are_gofr_dig_errors(self):
        """Test all custom errors inherit from GofrDigError."""
        errors = [
            ValidationError("CODE", "message"),
            ResourceNotFoundError("CODE", "message"),
            SecurityError("CODE", "message"),
            ConfigurationError("CODE", "message"),
            RegistryError("message"),
        ]

        for error in errors:
            assert isinstance(error, GofrDigError), f"{type(error).__name__} should inherit from GofrDigError"

    def test_all_errors_are_exceptions(self):
        """Test all custom errors are Exceptions."""
        errors = [
            GofrDigError("CODE", "message"),
            ValidationError("CODE", "message"),
            ResourceNotFoundError("CODE", "message"),
            SecurityError("CODE", "message"),
            ConfigurationError("CODE", "message"),
            RegistryError("message"),
        ]

        for error in errors:
            assert isinstance(error, Exception), f"{type(error).__name__} should be an Exception"

    def test_catch_hierarchy(self):
        """Test exception catch hierarchy works correctly."""
        caught_as = []

        try:
            raise ValidationError("TEST", "test")
        except ValidationError:
            caught_as.append("ValidationError")
        except GofrDigError:
            caught_as.append("GofrDigError")
        except Exception:
            caught_as.append("Exception")

        assert caught_as == ["ValidationError"]

        caught_as = []
        try:
            raise ValidationError("TEST", "test")
        except GofrDigError:
            caught_as.append("GofrDigError")
        except Exception:
            caught_as.append("Exception")

        assert caught_as == ["GofrDigError"]
