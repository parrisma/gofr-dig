"""Tests for error mapper functionality.

Phase 9: Tests for error_to_mcp_response and error_to_web_response functions.

These tests verify:
1. Error response structure is correct
2. Recovery strategies are included
3. Error codes are properly generated
4. All error types map correctly
"""

from app.exceptions import (
    GofrDigError,
    ValidationError,
    ResourceNotFoundError,
    SecurityError,
    ConfigurationError,
)
from app.errors.mapper import (
    error_to_mcp_response,
    error_to_web_response,
    get_error_code,
    get_recovery_strategy,
    RECOVERY_STRATEGIES,
    create_error_response,
)


class TestGetErrorCode:
    """Tests for error code extraction from exceptions."""

    def test_simple_error_class(self):
        """Test simple error class name conversion."""
        error = ValidationError("TEST", "test message")
        code = get_error_code(error)
        assert code == "VALIDATION"

    def test_compound_error_class(self):
        """Test compound error class name conversion."""
        error = ResourceNotFoundError("TEST", "test message")
        code = get_error_code(error)
        assert code == "RESOURCE_NOT_FOUND"

    def test_security_error(self):
        """Test security error class name conversion."""
        error = SecurityError("TEST", "test message")
        code = get_error_code(error)
        assert code == "SECURITY"

    def test_configuration_error(self):
        """Test configuration error class name conversion."""
        error = ConfigurationError("TEST", "test message")
        code = get_error_code(error)
        assert code == "CONFIGURATION"

    def test_base_error_class(self):
        """Test base GofrDigError class name conversion.
        
        Note: GofrDigError is now an alias for gofr_common.GofrError,
        so the class name is 'GofrError' -> 'GOFR'.
        """
        error = GofrDigError("TEST", "test message")
        code = get_error_code(error)
        assert code == "GOFR"


class TestGetRecoveryStrategy:
    """Tests for recovery strategy lookup."""

    def test_known_strategy_lookup(self):
        """Test lookup of known recovery strategy."""
        error = ValidationError("INVALID_URL", "Invalid URL")
        strategy = get_recovery_strategy("INVALID_URL", error)
        assert "http://" in strategy or "https://" in strategy

    def test_robots_blocked_strategy(self):
        """Test robots blocked has specific strategy."""
        error = GofrDigError("ROBOTS_BLOCKED", "Access blocked")
        strategy = get_recovery_strategy("ROBOTS_BLOCKED", error)
        assert "robots.txt" in strategy

    def test_rate_limited_strategy(self):
        """Test rate limited has specific strategy."""
        error = GofrDigError("RATE_LIMITED", "Too many requests")
        strategy = get_recovery_strategy("RATE_LIMITED", error)
        assert "rate_limit_delay" in strategy

    def test_fallback_for_validation_error(self):
        """Test fallback strategy for unknown ValidationError."""
        error = ValidationError("UNKNOWN_CODE", "Unknown validation error")
        strategy = get_recovery_strategy("UNKNOWN_CODE", error)
        assert "validation" in strategy.lower()

    def test_fallback_for_resource_not_found(self):
        """Test fallback strategy for unknown ResourceNotFoundError."""
        error = ResourceNotFoundError("UNKNOWN_CODE", "Unknown resource error")
        strategy = get_recovery_strategy("UNKNOWN_CODE", error)
        assert "resource" in strategy.lower() or "verify" in strategy.lower()

    def test_fallback_for_security_error(self):
        """Test fallback strategy for unknown SecurityError."""
        error = SecurityError("UNKNOWN_CODE", "Unknown security error")
        strategy = get_recovery_strategy("UNKNOWN_CODE", error)
        assert "authentication" in strategy.lower() or "authorization" in strategy.lower()

    def test_generic_fallback(self):
        """Test generic fallback for unknown error type."""
        error = GofrDigError("TOTALLY_UNKNOWN", "Some error")
        strategy = get_recovery_strategy("TOTALLY_UNKNOWN", error)
        assert len(strategy) > 0  # Should have some strategy


class TestRecoveryStrategies:
    """Tests for recovery strategies completeness."""

    def test_url_errors_have_strategies(self):
        """Test URL-related errors have recovery strategies."""
        url_errors = ["INVALID_URL", "URL_NOT_FOUND", "FETCH_ERROR", "TIMEOUT_ERROR", "CONNECTION_ERROR"]
        for code in url_errors:
            assert code in RECOVERY_STRATEGIES, f"Missing strategy for {code}"

    def test_robots_errors_have_strategies(self):
        """Test robots/access errors have recovery strategies."""
        access_errors = ["ROBOTS_BLOCKED", "ACCESS_DENIED", "RATE_LIMITED"]
        for code in access_errors:
            assert code in RECOVERY_STRATEGIES, f"Missing strategy for {code}"

    def test_extraction_errors_have_strategies(self):
        """Test content extraction errors have recovery strategies."""
        extraction_errors = ["SELECTOR_NOT_FOUND", "INVALID_SELECTOR", "EXTRACTION_ERROR"]
        for code in extraction_errors:
            assert code in RECOVERY_STRATEGIES, f"Missing strategy for {code}"

    def test_antidetection_errors_have_strategies(self):
        """Test anti-detection errors have recovery strategies."""
        antidetection_errors = ["INVALID_PROFILE", "INVALID_HEADERS"]
        for code in antidetection_errors:
            assert code in RECOVERY_STRATEGIES, f"Missing strategy for {code}"

    def test_crawl_errors_have_strategies(self):
        """Test crawl errors have recovery strategies."""
        crawl_errors = ["MAX_DEPTH_EXCEEDED", "MAX_PAGES_EXCEEDED"]
        for code in crawl_errors:
            assert code in RECOVERY_STRATEGIES, f"Missing strategy for {code}"


class TestErrorToMCPResponse:
    """Tests for MCP response format."""

    def test_basic_structure(self):
        """Test MCP response has required fields."""
        error = ValidationError("INVALID_URL", "URL is malformed")
        response = error_to_mcp_response(error)

        assert response["success"] is False
        assert "error_code" in response
        assert "message" in response
        assert "recovery_strategy" in response
        assert "details" in response

    def test_error_code_included(self):
        """Test error code is properly included."""
        error = ValidationError("INVALID_URL", "URL is malformed")
        response = error_to_mcp_response(error)

        # Error code is derived from class name
        assert response["error_code"] == "VALIDATION"

    def test_message_from_exception(self):
        """Test message comes from exception."""
        error = ValidationError("TEST", "This is the error message")
        response = error_to_mcp_response(error)

        assert "This is the error message" in response["message"]

    def test_recovery_strategy_present(self):
        """Test recovery strategy is included."""
        error = GofrDigError("ROBOTS_BLOCKED", "Blocked by robots.txt")
        response = error_to_mcp_response(error)

        assert len(response["recovery_strategy"]) > 0

    def test_details_included_when_present(self):
        """Test details are included when provided."""
        error = ValidationError(
            "INVALID_URL",
            "URL is malformed",
            details={"url": "not-a-url", "reason": "missing scheme"},
        )
        response = error_to_mcp_response(error)

        assert response["details"]["url"] == "not-a-url"
        assert response["details"]["reason"] == "missing scheme"

    def test_details_empty_dict_when_not_provided(self):
        """Test details is empty dict when not provided."""
        error = ValidationError("TEST", "test message")
        response = error_to_mcp_response(error)

        assert response["details"] == {}


class TestErrorToWebResponse:
    """Tests for web API response format."""

    def test_basic_structure(self):
        """Test web response has nested error object."""
        error = ValidationError("INVALID_URL", "URL is malformed")
        response = error_to_web_response(error)

        assert "error" in response
        assert "code" in response["error"]
        assert "message" in response["error"]
        assert "recovery" in response["error"]
        assert "details" in response["error"]

    def test_error_code_in_nested_object(self):
        """Test error code is in nested error object."""
        error = ResourceNotFoundError("NOT_FOUND", "Resource missing")
        response = error_to_web_response(error)

        assert response["error"]["code"] == "RESOURCE_NOT_FOUND"

    def test_message_in_nested_object(self):
        """Test message is in nested error object."""
        error = SecurityError("DENIED", "Access denied")
        response = error_to_web_response(error)

        assert "Access denied" in response["error"]["message"]


class TestCreateErrorResponse:
    """Tests for the ErrorResponse object creation."""

    def test_creates_error_response(self):
        """Test create_error_response returns proper object."""
        error = ValidationError("TEST", "test message")
        response = create_error_response(error)

        assert hasattr(response, "error_code")
        assert hasattr(response, "message")
        assert hasattr(response, "recovery_strategy")
        assert hasattr(response, "details")


class TestErrorMapperIntegration:
    """Integration tests for error mapper with real exceptions."""

    def test_validation_error_full_flow(self):
        """Test full flow with ValidationError."""
        error = ValidationError(
            code="INVALID_URL",
            message="The URL 'not-valid' is not a valid HTTP URL",
            details={"provided_url": "not-valid"},
        )

        mcp_response = error_to_mcp_response(error)
        web_response = error_to_web_response(error)

        # MCP format
        assert mcp_response["success"] is False
        # Recovery strategy is looked up from RECOVERY_STRATEGIES or falls back to generic
        assert len(mcp_response["recovery_strategy"]) > 0

        # Web format
        assert "code" in web_response["error"]

    def test_security_error_full_flow(self):
        """Test full flow with SecurityError."""
        error = SecurityError(
            code="ACCESS_DENIED",
            message="Server returned 403 Forbidden",
            details={"status_code": 403},
        )

        mcp_response = error_to_mcp_response(error)

        assert mcp_response["success"] is False
        assert mcp_response["details"]["status_code"] == 403

    def test_resource_not_found_error_full_flow(self):
        """Test full flow with ResourceNotFoundError."""
        error = ResourceNotFoundError(
            code="URL_NOT_FOUND",
            message="Server returned 404 Not Found",
            details={"url": "http://example.com/missing", "status_code": 404},
        )

        mcp_response = error_to_mcp_response(error)

        assert mcp_response["success"] is False
        # Recovery strategy is looked up from RECOVERY_STRATEGIES or falls back to generic
        assert len(mcp_response["recovery_strategy"]) > 0
