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


# Recovery strategy templates for common error types in web scraping
RECOVERY_STRATEGIES: Dict[str, str] = {
    # URL and fetch errors
    "INVALID_URL": "Ensure the URL is properly formatted with http:// or https:// scheme.",
    "URL_NOT_FOUND": "Verify the URL exists and is accessible. The server returned 404.",
    "FETCH_ERROR": "Check network connectivity and that the target site is online. Try again later.",
    "TIMEOUT_ERROR": "The request timed out. Try increasing timeout or check if the site is slow/unresponsive.",
    "CONNECTION_ERROR": "Could not connect to the server. Verify the URL and check network connectivity.",
    
    # Robots.txt and access
    "ROBOTS_BLOCKED": "Access blocked by robots.txt. Use set_antidetection with respect_robots_txt=false to override (use responsibly).",
    "ACCESS_DENIED": "The server denied access. Try using a different anti-detection profile or custom headers.",
    "RATE_LIMITED": "Too many requests. Increase rate_limit_delay in set_antidetection settings.",
    
    # Content extraction errors
    "SELECTOR_NOT_FOUND": "The CSS selector matched no elements. Verify the selector syntax and that the element exists on the page.",
    "INVALID_SELECTOR": "The CSS selector syntax is invalid. Check for typos and proper CSS selector format.",
    "EXTRACTION_ERROR": "Failed to extract content. The page may have unexpected structure or encoding.",
    "ENCODING_ERROR": "Character encoding issue. The page may use an unsupported encoding.",
    
    # Anti-detection errors
    "INVALID_PROFILE": "Use one of: 'stealth', 'balanced', 'none', or 'custom' for anti-detection profile.",
    "INVALID_HEADERS": "Custom headers must be a dictionary with string keys and values.",
    
    # Crawl errors
    "MAX_DEPTH_EXCEEDED": "Crawl depth is limited to 3. Use depth=1, 2, or 3.",
    "MAX_PAGES_EXCEEDED": "Too many pages requested. Reduce max_pages_per_level (max 20).",
    
    # Configuration errors
    "CONFIGURATION_ERROR": "Check server configuration. Contact administrator if issue persists.",
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
