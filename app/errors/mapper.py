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

try:
    from app.validation.document_models import ErrorResponse  # type: ignore[import-not-found]
except ImportError:
    # Placeholder if module doesn't exist
    class ErrorResponse:  # type: ignore[no-redef]
        """Placeholder ErrorResponse when validation module is not available."""
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)


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
    "INVALID_COLUMN_WIDTH": "Column widths must be percentages (e.g., '25%') and total <= 100%.",
    "STYLE_NOT_FOUND": "Use list_styles to see available styles for your group.",
    "GROUP_MISMATCH": "Ensure the resource belongs to your group. Check group_id in your request.",
    "CONFIGURATION_ERROR": "Check server logs for configuration details. Contact administrator if issue persists.",
}


def get_error_code(error: GofrDigError) -> str:
    """Extract error code from exception class name.
    
    Converts class names like TemplateNotFoundError to TEMPLATE_NOT_FOUND.
    """
    name = error.__class__.__name__
    # Remove 'Error' suffix
    if name.endswith("Error"):
        name = name[:-5]
    # Convert camelCase to UPPER_SNAKE_CASE
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.upper())
    return "".join(result)


def get_recovery_strategy(error_code: str, error: GofrDigError) -> str:
    """Get recovery strategy for an error.
    
    Returns specific strategy if available, otherwise a generic one.
    """
    if error_code in RECOVERY_STRATEGIES:
        return RECOVERY_STRATEGIES[error_code]
    
    # Generic strategies based on error type
    if isinstance(error, ResourceNotFoundError):
        return "Verify the resource identifier and check that the resource exists."
    elif isinstance(error, ValidationError):
        return "Review the validation error details and correct the input."
    elif isinstance(error, SecurityError):
        return "Ensure proper authentication and authorization. Check your credentials."
    
    return "Review the error message and try again. Contact support if the issue persists."


def create_error_response(error: GofrDigError) -> ErrorResponse:
    """Create a structured error response from a GofrDigError.
    
    Args:
        error: The exception to convert
        
    Returns:
        ErrorResponse with error_code, message, details, and recovery_strategy
    """
    error_code = get_error_code(error)
    
    # Get details if available
    details: Dict[str, Any] = {}
    if hasattr(error, "details") and error.details:  # type: ignore[union-attr]
        details = error.details  # type: ignore[union-attr]
    
    # Build error response
    if isinstance(error, (ResourceNotFoundError, ValidationError, SecurityError)):
        return ErrorResponse(
            error_code=error_code,
            message=str(error),
            details=details,
            recovery_strategy=get_recovery_strategy(error_code, error),
        )
    
    # Generic GofrDigError
    return ErrorResponse(
        error_code=error_code,
        message=str(error),
        details=details,
        recovery_strategy=get_recovery_strategy(error_code, error),
    )


def error_to_mcp_response(error: GofrDigError) -> Dict[str, Any]:
    """Convert error to MCP-compatible response format.
    
    Args:
        error: The exception to convert
        
    Returns:
        Dictionary suitable for MCP tool response
    """
    response = create_error_response(error)
    return {
        "success": False,
        "error_code": response.error_code,  # type: ignore[attr-defined]
        "message": response.message,  # type: ignore[attr-defined]
        "details": response.details,  # type: ignore[attr-defined]
        "recovery_strategy": response.recovery_strategy,  # type: ignore[attr-defined]
    }


def error_to_web_response(error: GofrDigError) -> Dict[str, Any]:
    """Convert error to web API response format.
    
    Args:
        error: The exception to convert
        
    Returns:
        Dictionary suitable for FastAPI response
    """
    response = create_error_response(error)
    return {
        "error": {
            "code": response.error_code,  # type: ignore[attr-defined]
            "message": response.message,  # type: ignore[attr-defined]
            "details": response.details,  # type: ignore[attr-defined]
            "recovery": response.recovery_strategy,  # type: ignore[attr-defined]
        }
    }
