"""Application configuration

Centralized configuration for data persistence paths.
Allows easy override for testing with temporary directories.
"""

import os
from pathlib import Path
from typing import Optional


# Add public storage dir function
def get_public_storage_dir() -> str:
    """Get public storage directory as string"""
    return str(Config.get_storage_dir() / "public")


class Config:
    """Application configuration with support for testing overrides"""

    _test_mode: bool = False
    _test_data_dir: Optional[Path] = None

    @classmethod
    def get_data_dir(cls) -> Path:
        """
        Get the data directory for persistent storage

        Returns:
            Path to data directory (configurable via GOFR_DIG_DATA_DIR environment variable)

        Default locations:
            - Production: /home/{user}/devroot/gofr-dig/data
            - Testing: Temporary directory set by tests
            - Docker: Can be overridden via GOFR_DIG_DATA_DIR env var
        """
        if cls._test_mode and cls._test_data_dir:
            return cls._test_data_dir

        # Check environment variable for data directory
        env_data_dir = os.environ.get("GOFR_DIG_DATA_DIR")
        if env_data_dir:
            return Path(env_data_dir)

        # Default to project data directory
        # This assumes we're running from /home/{user}/devroot/gofr-dig
        project_root = Path(__file__).parent.parent
        return project_root / "data"

    @classmethod
    def get_storage_dir(cls) -> Path:
        """
        Get the directory for image storage

        Returns:
            Path to storage directory within data folder
        """
        return cls.get_data_dir() / "storage"

    @classmethod
    def get_sessions_dir(cls) -> Path:
        """Get the directory for document session storage."""

        return cls.get_data_dir() / "sessions"

    @classmethod
    def get_proxy_dir(cls) -> Path:
        """Get the directory for proxy-stored rendered documents."""
        return cls.get_data_dir() / "storage"

    @classmethod
    def get_auth_dir(cls) -> Path:
        """
        Get the directory for authentication data

        Returns:
            Path to auth directory within data folder
        """
        return cls.get_data_dir() / "auth"

    @classmethod
    def get_token_store_path(cls) -> Path:
        """
        Get the path to the token store file

        Returns:
            Path to token store JSON file
        """
        return cls.get_data_dir() / "auth" / "tokens.json"

    @classmethod
    def set_test_mode(cls, test_data_dir: Optional[Path] = None) -> None:
        """
        Enable test mode with optional custom data directory

        Args:
            test_data_dir: Optional path to use for test data (if None, uses temp dir)
        """
        cls._test_mode = True
        cls._test_data_dir = test_data_dir

    @classmethod
    def clear_test_mode(cls) -> None:
        """Disable test mode and return to normal configuration"""
        cls._test_mode = False
        cls._test_data_dir = None

    @classmethod
    def is_test_mode(cls) -> bool:
        """Check if currently in test mode"""
        return cls._test_mode


# Convenience functions for backward compatibility
def get_default_storage_dir() -> str:
    """Get default storage directory as string"""
    return str(Config.get_storage_dir())


def get_default_token_store_path() -> str:
    """Get default token store path as string"""
    return str(Config.get_token_store_path())


def get_default_sessions_dir() -> str:
    """Get default sessions directory as string."""

    return str(Config.get_sessions_dir())


def get_default_proxy_dir() -> str:
    """Get default proxy directory as string."""
    return str(Config.get_proxy_dir())
