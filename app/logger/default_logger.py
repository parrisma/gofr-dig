import sys
import uuid
from datetime import datetime
from typing import Any, TextIO
from .interface import Logger


class DefaultLogger(Logger):
    """Default logger implementation with session tracking"""

    def __init__(self, output: TextIO = sys.stderr, include_timestamp: bool = True):
        """
        Initialize the default logger

        Args:
            output: Output stream (default: stderr)
            include_timestamp: Whether to include timestamps in log messages
        """
        self._session_id = str(uuid.uuid4())
        self._output = output
        self._include_timestamp = include_timestamp

    def get_session_id(self) -> str:
        """Get the current session ID"""
        return self._session_id

    def _format_message(self, level: str, message: str, **kwargs: Any) -> str:
        """Format a log message with session ID and optional timestamp"""
        parts = []

        if self._include_timestamp:
            timestamp = datetime.utcnow().isoformat() + "Z"
            parts.append(timestamp)

        parts.append(f"[{level}]")
        parts.append(f"[session:{self._session_id[:8]}]")
        parts.append(message)

        # Add any additional key-value pairs
        if kwargs:
            extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
            parts.append(f"({extra})")

        return " ".join(parts)

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """Internal logging method"""
        formatted = self._format_message(level, message, **kwargs)
        print(formatted, file=self._output, flush=True)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message"""
        self._log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message"""
        self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message"""
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error message"""
        self._log("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log a critical message"""
        self._log("CRITICAL", message, **kwargs)
