"""Logger module for gofr-dig

Re-exports from gofr_common.logger for backward compatibility.

Usage:
    from app.logger import Logger, DefaultLogger

    # Use the default logger
    logger = DefaultLogger()
    logger.info("Application started")

    # Or implement your own
    class MyCustomLogger(Logger):
        def info(self, message: str, **kwargs):
            # Your custom implementation
            pass
"""

from gofr_common.logger import Logger, get_logger
from typing import Any, cast
from .default_logger import DefaultLogger
from .console_logger import ConsoleLogger
from app.build_info import BUILD_NUMBER

# Shared logger instance configured from environment.
# Uses StructuredLogger under gofr_common and honors GOFR_DIG_LOG_* settings.
session_logger: Logger = get_logger("gofr-dig")

# Inject build_number into every log event via the logger's extra defaults.
# StructuredLogger._log merges extra into each record, so we patch it once.
_logger_obj = cast(Any, session_logger)
if hasattr(_logger_obj, "_default_extra"):
    _logger_obj._default_extra["build_number"] = BUILD_NUMBER
else:
    _logger_obj._default_extra = {"build_number": BUILD_NUMBER}

__all__ = [
    "Logger",
    "DefaultLogger",
    "ConsoleLogger",
    "session_logger",
]
