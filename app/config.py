"""Application configuration

Re-exports configuration from gofr_common.config with GOFR_DIG prefix.
"""

from pathlib import Path

from gofr_common.config import (
    Config as BaseConfig,
    Settings,
    ServerSettings,
    AuthSettings,
    StorageSettings,
    LogSettings,
    get_settings as _get_settings,
    reset_settings,
)

# Project-specific prefix
_ENV_PREFIX = "GOFR_DIG"

# Project root for default data directory
_PROJECT_ROOT = Path(__file__).parent.parent


class Config(BaseConfig):
    """Project-specific Config with GOFR_DIG prefix"""

    _env_prefix = _ENV_PREFIX


def get_settings(reload: bool = False, require_auth: bool = True) -> Settings:
    """Get settings with GOFR_DIG prefix"""
    return _get_settings(
        prefix=_ENV_PREFIX,
        reload=reload,
        require_auth=require_auth,
        project_root=_PROJECT_ROOT,
    )


# Convenience functions
def get_public_storage_dir() -> str:
    """Get public storage directory as string"""
    return str(Config.get_storage_dir() / "public")


def get_default_storage_dir() -> str:
    """Get default storage directory as string"""
    return str(Config.get_storage_dir())


def get_default_token_store_path() -> str:
    """Get default token store path as string"""
    return str(Config.get_token_store_path())


def get_default_sessions_dir() -> str:
    """Get default sessions directory as string"""
    return str(Config.get_sessions_dir())


def get_default_proxy_dir() -> str:
    """Get default proxy directory as string"""
    return str(Config.get_proxy_dir())


__all__ = [
    "Config",
    "Settings",
    "ServerSettings",
    "AuthSettings",
    "StorageSettings",
    "LogSettings",
    "get_settings",
    "reset_settings",
    "get_public_storage_dir",
    "get_default_storage_dir",
    "get_default_token_store_path",
    "get_default_sessions_dir",
    "get_default_proxy_dir",
]
