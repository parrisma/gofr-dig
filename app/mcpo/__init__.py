"""MCPO wrapper for GOFR-DIG MCP server

This module provides MCPO (MCP-to-OpenAPI) proxy functionality
to expose the GOFR-DIG MCP server as OpenAPI-compatible endpoints.
"""

from app.mcpo.wrapper import start_mcpo_wrapper

__all__ = ["start_mcpo_wrapper"]
