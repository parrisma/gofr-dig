"""Error response mapping for MCP and web interfaces.

Converts structured GofrDigError exceptions into standardized error responses
with machine-readable error codes and recovery strategies.
"""

from typing import Dict, Any
from app.exceptions import (
    GofrDigError,
    ValidationError,
    ResourceNotFoundError,
    SecurityError,
)
from app.validation.document_models import ErrorResponse


# Recovery strategy templates for common error types
RECOVERY_STRATEGIES: Dict[str, str] = {
    "SESSION_NOT_FOUND": "Verify the session_id is correct and belongs to your group. Call list_active_sessions to see your sessions.",
    "TEMPLATE_NOT_FOUND": "Use list_templates to see available templates for your group.",
    "FRAGMENT_NOT_FOUND": "Call list_session_fragments to see current fragment instances and their GUIDs.",
    "INVALID_FRAGMENT_PARAMETERS": "Call get_fragment_details to see required and optional parameters for this fragment type.",
    "INVALID_GLOBAL_PARAMETERS": "Call get_template_details to see required global parameters for this template.",
    "INVALID_POSITION": "Use 'start', 'end', 'before:<guid>', or 'after:<guid>' format. Call list_session_fragments to get valid GUIDs.",
    "INVALID_SESSION_STATE": "Ensure global parameters are set before adding fragments or rendering.",
    "INVALID_TABLE_DATA": "Review table validation requirements in documentation. Ensure rows are consistent and required parameters are provided.",
    "INVALID_COLOR": "Use theme colors (blue, orange, green, red, purple, etc.) or hex format (#RRGGBB or #RGB).",
    "NUMBER_FORMAT_ERROR": "Use format specifications like 'currency:USD', 'percent', 'decimal:2', 'integer', or 'accounting'.",
    "INVALID_COLUMN_WIDTH": "Column widths must be percentages (e.g., '25%') and total ≤ 100%.",
    "STYLE_NOT_FOUND": "Use list_styles to see available styles for your group.",
    "REGISTRY_ERROR": "Check that template/fragment/style ID is valid and exists in the system.",
    "VALIDATION_ERROR": "Review the error message and adjust the request parameters accordingly.",
    "RESOURCE_NOT_FOUND": "Verify the resource ID is correct and the resource exists.",
    "SECURITY_ERROR": "Ensure your authentication token has access to the requested resource.",
}


def get_recovery_strategy(error_code: str) -> str:
    """Get recovery strategy for an error code.

    Args:
        error_code: The error code

    Returns:
        Recovery strategy string
    """
    return RECOVERY_STRATEGIES.get(
        error_code, "Review the error message, adjust the request, and try again."
    )


def map_exception_to_response(error: Exception) -> ErrorResponse:
    """Convert an exception to a structured ErrorResponse.

    Args:
        error: The exception to convert

    Returns:
        ErrorResponse with structured error information
    """
    if isinstance(error, GofrDigError):
        # Structured GOFR-DIG error with code, message, details
        return ErrorResponse(
            error_code=error.code,
            message=error.message,
            details=error.details if error.details else None,
            recovery_strategy=get_recovery_strategy(error.code),
        )

    # Handle Pydantic validation errors
    from pydantic import ValidationError as PydanticValidationError

    if isinstance(error, PydanticValidationError):
        errors = error.errors()
        return ErrorResponse(
            error_code="PYDANTIC_VALIDATION_ERROR",
            message=f"Validation failed: {len(errors)} error(s)",
            details={"errors": errors},
            recovery_strategy="Check the error details and provide valid input according to the schema.",
        )

    # Generic exceptions - wrap with minimal structure
    return ErrorResponse(
        error_code="INTERNAL_ERROR",
        message=str(error),
        details={"exception_type": type(error).__name__},
        recovery_strategy="An unexpected error occurred. Please report this issue if it persists.",
    )


def map_error_for_mcp(error: Exception) -> Dict[str, Any]:
    """Map exception to MCP tool response format.

    Args:
        error: The exception to convert

    Returns:
        Dictionary suitable for MCP tool response
    """
    response = map_exception_to_response(error)

    return {
        "status": "error",
        "error_code": response.error_code,
        "message": response.message,
        "details": response.details,
        "recovery_strategy": response.recovery_strategy,
    }


def map_error_for_web(error: Exception, status_code: int = 400) -> Dict[str, Any]:
    """Map exception to web API response format.

    Args:
        error: The exception to convert
        status_code: HTTP status code (default 400)

    Returns:
        Dictionary suitable for FastAPI JSONResponse
    """
    response = map_exception_to_response(error)

    return {
        "status": "error",
        "error": {
            "code": response.error_code,
            "message": response.message,
            "details": response.details,
            "recovery": response.recovery_strategy,
        },
    }


def get_http_status_for_error(error: Exception) -> int:
    """Determine appropriate HTTP status code for an error.

    Args:
        error: The exception

    Returns:
        HTTP status code
    """
    if isinstance(error, ResourceNotFoundError):
        return 404
    elif isinstance(error, SecurityError):
        return 403
    elif isinstance(error, ValidationError):
        return 400
    elif isinstance(error, GofrDigError):
        return 400
    else:
        return 500
