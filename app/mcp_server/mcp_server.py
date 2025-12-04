#!/usr/bin/env python3
"""GOFR-DIG MCP Server - Hello World Implementation."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, AsyncIterator, Dict, List

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool

from app.logger import session_logger as logger

app = Server("gofr-dig-service")


def _json_text(data: Dict[str, Any]) -> TextContent:
    """Create JSON text content."""
    return TextContent(type="text", text=json.dumps(data, indent=2))


@app.list_tools()
async def handle_list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="ping",
            description="Health check - returns server status",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="hello_world",
            description="Returns a greeting message",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Optional name to greet",
                    }
                },
            },
        ),
    ]


@app.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool invocations."""
    logger.info("Tool called", tool=name, args=arguments)

    if name == "ping":
        return [_json_text({"status": "ok", "service": "gofr-dig"})]

    if name == "hello_world":
        greeting_name = arguments.get("name", "World")
        return [_json_text({"message": f"Hello, {greeting_name}!"})]

    return [_json_text({"error": f"Unknown tool: {name}"})]


async def initialize_server() -> None:
    """Initialize server components."""
    logger.info("GOFR-DIG server initialized")


# Streamable HTTP setup
session_manager_http = StreamableHTTPSessionManager(
    app=app,
    event_store=None,
    json_response=False,
    stateless=False,
)


async def handle_streamable_http(scope, receive, send) -> None:
    """Handle HTTP requests."""
    await session_manager_http.handle_request(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(starlette_app) -> AsyncIterator[None]:
    """Manage server lifecycle."""
    logger.info("Starting GOFR-DIG server")
    await initialize_server()
    async with session_manager_http.run():
        yield


from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount

starlette_app = Starlette(
    debug=False,
    routes=[Mount("/mcp/", app=handle_streamable_http)],
    lifespan=lifespan,
)

starlette_app = CORSMiddleware(
    starlette_app,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    expose_headers=["Mcp-Session-Id"],
)


async def main(host: str = "0.0.0.0", port: int = 8030) -> None:
    """Run the server."""
    import uvicorn

    config = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
