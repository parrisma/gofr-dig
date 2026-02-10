"""MCPO configuration management

Handles generation of mcpo config files for multiple server configurations.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional


class MCPOConfig:
    """MCPO configuration builder"""

    def __init__(self):
        self.servers: Dict[str, dict] = {}

    def add_server(
        self,
        name: str,
        url: str,
        auth_token: Optional[str] = None,
        disabled_tools: Optional[List[str]] = None,
    ) -> None:
        """
        Add an MCP server to the configuration

        Args:
            name: Unique name for this server instance
            url: URL of the MCP server endpoint
            auth_token: Optional JWT bearer token for authentication
            disabled_tools: Optional list of tool names to disable
        """
        from typing import Any

        server_config: Dict[str, Any] = {
            "type": "streamable-http",
            "url": url,
        }

        if auth_token:
            server_config["headers"] = {"Authorization": f"Bearer {auth_token}"}

        if disabled_tools:
            server_config["disabledTools"] = disabled_tools

        self.servers[name] = server_config

    def to_dict(self) -> dict:
        """Convert configuration to dictionary"""
        return {"mcpServers": self.servers}

    def to_json(self, indent: int = 2) -> str:
        """Convert configuration to JSON string"""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: Path) -> None:
        """Save configuration to file"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: Path) -> "MCPOConfig":
        """Load configuration from file"""
        with open(path, "r") as f:
            data = json.load(f)

        config = cls()
        config.servers = data.get("mcpServers", {})
        return config


def create_default_config(
    auth_token: Optional[str] = None,
    mcp_auth_port: int = int(os.environ.get("GOFR_DIG_MCP_PORT", "0")),
    mcp_public_port: int = 8015,
) -> MCPOConfig:
    """
    Create default MCPO configuration with both auth and public servers

    Args:
        auth_token: JWT token for authenticated server
        mcp_auth_port: Port for authenticated MCP server
        mcp_public_port: Port for public MCP server

    Returns:
        MCPOConfig instance
    """
    config = MCPOConfig()

    # Add authenticated server
    config.add_server(
        name="gofr-dig-auth",
        url=f"http://localhost:{mcp_auth_port}/mcp",
        auth_token=auth_token,
    )

    # Add public server (no auth)
    config.add_server(
        name="gofr-dig-public",
        url=f"http://localhost:{mcp_public_port}/mcp",
    )

    return config


def create_public_only_config(
    mcp_port: int = int(os.environ.get("GOFR_DIG_MCP_PORT", "0")),
) -> MCPOConfig:
    """
    Create MCPO configuration for public (no auth) server only

    Args:
        mcp_port: Port for public MCP server

    Returns:
        MCPOConfig instance
    """
    config = MCPOConfig()
    config.add_server(
        name="gofr-dig",
        url=f"http://localhost:{mcp_port}/mcp",
    )
    return config
