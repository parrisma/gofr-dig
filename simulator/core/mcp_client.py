from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.logger import Logger, session_logger

from mcp import ClientSession
from mcp.client import streamable_http
from mcp.types import TextContent


streamable_http_client = streamable_http.streamablehttp_client


@dataclass(frozen=True)
class MCPCallResult:
    success: bool
    error: str | None
    payload: dict[str, Any] | None


class MCPToolClient:
    """Thin wrapper around the MCP streamable-http client used by gofr-dig tests."""

    def __init__(self, mcp_url: str, *, logger: Logger | None = None) -> None:
        self._mcp_url = mcp_url
        self._logger = logger or session_logger
        self._transport_cm = None
        self._session_cm = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "MCPToolClient":
        self._transport_cm = streamable_http_client(self._mcp_url)
        read, write, _ = await self._transport_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session_cm is not None:
            await self._session_cm.__aexit__(exc_type, exc, tb)
            self._session_cm = None
            self._session = None
        if self._transport_cm is not None:
            await self._transport_cm.__aexit__(exc_type, exc, tb)
            self._transport_cm = None

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPCallResult:
        try:
            if self._session is None:
                raise RuntimeError("MCPToolClient must be used as an async context manager")

            result = await self._session.call_tool(tool_name, arguments)

            if not result.content:
                return MCPCallResult(success=False, error="empty_mcp_response", payload=None)

            first = result.content[0]
            if not isinstance(first, TextContent):
                return MCPCallResult(success=False, error="non_text_mcp_response", payload=None)

            text = first.text
            try:
                payload = json.loads(text)
            except Exception:
                return MCPCallResult(success=False, error="non_json_mcp_response", payload=None)

            success = bool(payload.get("success", True))
            return MCPCallResult(
                success=success,
                error=None if success else payload.get("error") or payload.get("message"),
                payload=payload,
            )
        except Exception as exc:
            self._logger.warning(
                "sim.mcp_call_failed",
                event="sim.mcp_call_failed",
                tool_name=tool_name,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return MCPCallResult(success=False, error=str(exc), payload=None)
