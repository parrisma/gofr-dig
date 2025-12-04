"""Test hello_world MCP tool."""

import json
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


@pytest.fixture
def mcp_url():
    """MCP server URL."""
    return "http://localhost:8030/mcp"


def extract_text(result) -> str:
    """Extract text from MCP result."""
    if result.content and len(result.content) > 0:
        return result.content[0].text
    return ""


def parse_json(result) -> dict:
    """Parse JSON from MCP result."""
    text = extract_text(result)
    return json.loads(text)


@pytest.mark.asyncio
async def test_hello_world_default(mcp_url):
    """Test hello_world with default greeting."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("hello_world", {})
            data = parse_json(result)

            assert data["message"] == "Hello, World!"


@pytest.mark.asyncio
async def test_hello_world_with_name(mcp_url):
    """Test hello_world with custom name."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("hello_world", {"name": "Claude"})
            data = parse_json(result)

            assert data["message"] == "Hello, Claude!"


@pytest.mark.asyncio
async def test_ping(mcp_url):
    """Test ping health check."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("ping", {})
            data = parse_json(result)

            assert data["status"] == "ok"
            assert data["service"] == "gofr-dig"
