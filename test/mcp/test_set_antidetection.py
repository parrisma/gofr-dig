"""Tests for set_antidetection MCP tool.

Tests the anti-detection configuration tool for web scraping.
"""

import json
from typing import Any, List

import pytest

from app.scraping import AntiDetectionManager, AntiDetectionProfile
from app.scraping.state import get_scraping_state, reset_scraping_state


def get_mcp_result_data(result: Any) -> dict:
    """Extract JSON data from MCP tool result."""
    result_list: List[Any] = result  # type: ignore[assignment]
    return json.loads(result_list[0].text)  # type: ignore[union-attr]


class TestAntiDetectionProfile:
    """Tests for AntiDetectionProfile enum."""

    def test_profile_values(self):
        """Test that all profile values are correct."""
        assert AntiDetectionProfile.STEALTH.value == "stealth"
        assert AntiDetectionProfile.BALANCED.value == "balanced"
        assert AntiDetectionProfile.NONE.value == "none"
        assert AntiDetectionProfile.CUSTOM.value == "custom"
        assert AntiDetectionProfile.BROWSER_TLS.value == "browser_tls"

    def test_profile_from_string(self):
        """Test creating profile from string."""
        assert AntiDetectionProfile("stealth") == AntiDetectionProfile.STEALTH
        assert AntiDetectionProfile("balanced") == AntiDetectionProfile.BALANCED
        assert AntiDetectionProfile("none") == AntiDetectionProfile.NONE
        assert AntiDetectionProfile("custom") == AntiDetectionProfile.CUSTOM
        assert AntiDetectionProfile("browser_tls") == AntiDetectionProfile.BROWSER_TLS

    def test_invalid_profile_raises(self):
        """Test that invalid profile string raises ValueError."""
        with pytest.raises(ValueError):
            AntiDetectionProfile("invalid")


class TestAntiDetectionManager:
    """Tests for AntiDetectionManager."""

    def test_default_profile_is_balanced(self):
        """Test that default profile is balanced."""
        manager = AntiDetectionManager()
        assert manager.profile == AntiDetectionProfile.BALANCED

    def test_none_profile_minimal_headers(self):
        """Test that NONE profile returns minimal headers."""
        manager = AntiDetectionManager(AntiDetectionProfile.NONE)
        headers = manager.get_headers()

        assert "User-Agent" in headers
        assert headers["User-Agent"] == "gofr-dig/1.0"
        assert "Accept" not in headers
        assert "Accept-Language" not in headers

    def test_balanced_profile_standard_headers(self):
        """Test that BALANCED profile returns standard browser headers."""
        manager = AntiDetectionManager(AntiDetectionProfile.BALANCED)
        headers = manager.get_headers()

        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert "Accept-Encoding" in headers
        # Should not have stealth headers
        assert "Sec-Ch-Ua" not in headers

    def test_stealth_profile_full_headers(self):
        """Test that STEALTH profile returns full browser emulation headers."""
        manager = AntiDetectionManager(AntiDetectionProfile.STEALTH)
        headers = manager.get_headers()

        assert "User-Agent" in headers
        assert "Accept" in headers
        assert "Accept-Language" in headers
        assert "Accept-Encoding" in headers
        # Stealth-specific headers
        assert "Sec-Ch-Ua" in headers
        assert "Sec-Fetch-Dest" in headers
        assert "Sec-Fetch-Mode" in headers

    def test_custom_profile_uses_custom_headers(self):
        """Test that CUSTOM profile uses provided custom headers."""
        custom_headers = {
            "X-Custom-Header": "custom-value",
            "Accept": "application/json",
        }
        manager = AntiDetectionManager(
            AntiDetectionProfile.CUSTOM,
            custom_headers=custom_headers,
            custom_user_agent="MyBot/1.0",
        )
        headers = manager.get_headers()

        assert headers["User-Agent"] == "MyBot/1.0"
        assert headers["X-Custom-Header"] == "custom-value"
        assert headers["Accept"] == "application/json"

    def test_user_agent_rotation(self):
        """Test that user agent can be rotated."""
        manager = AntiDetectionManager(AntiDetectionProfile.BALANCED)

        # Get initial user agent
        ua1 = manager.get_user_agent()

        # Without rotation, should return same UA
        ua2 = manager.get_user_agent(rotate=False)
        assert ua1 == ua2

        # With rotation, may return different UA (probabilistic)
        # We'll just verify it returns a valid string
        ua3 = manager.get_user_agent(rotate=True)
        assert isinstance(ua3, str)
        assert len(ua3) > 0

    def test_get_profile_info(self):
        """Test getting profile information."""
        manager = AntiDetectionManager(AntiDetectionProfile.STEALTH)
        info = manager.get_profile_info()

        assert info["profile"] == "stealth"
        assert "description" in info
        assert "user_agent" in info


class TestScrapingState:
    """Tests for scraping state management."""

    def setup_method(self):
        """Reset state before each test."""
        reset_scraping_state()

    def teardown_method(self):
        """Reset state after each test."""
        reset_scraping_state()

    def test_default_state_values(self):
        """Test that default state has expected values."""
        state = get_scraping_state()

        assert state.antidetection_profile == AntiDetectionProfile.BALANCED
        assert state.custom_headers == {}
        assert state.custom_user_agent is None
        assert state.respect_robots_txt is True
        assert state.rate_limit_delay == 1.0
        assert state.max_response_chars == 400000

    def test_state_is_singleton(self):
        """Test that get_scraping_state returns same instance."""
        state1 = get_scraping_state()
        state2 = get_scraping_state()

        assert state1 is state2

    def test_state_persists_modifications(self):
        """Test that state modifications persist."""
        state = get_scraping_state()
        state.antidetection_profile = AntiDetectionProfile.STEALTH
        state.rate_limit_delay = 2.5

        # Get state again
        state2 = get_scraping_state()
        assert state2.antidetection_profile == AntiDetectionProfile.STEALTH
        assert state2.rate_limit_delay == 2.5

    def test_reset_clears_state(self):
        """Test that reset clears the state."""
        state = get_scraping_state()
        state.antidetection_profile = AntiDetectionProfile.STEALTH

        reset_scraping_state()

        state2 = get_scraping_state()
        assert state2.antidetection_profile == AntiDetectionProfile.BALANCED


class TestSetAntidetectionMCPTool:
    """Integration tests for set_antidetection MCP tool via actual server."""

    def setup_method(self):
        """Reset scraping state before each test."""
        reset_scraping_state()

    def teardown_method(self):
        """Reset scraping state after each test."""
        reset_scraping_state()

    @pytest.mark.asyncio
    async def test_set_balanced_profile(self):
        """Test setting balanced profile via MCP tool."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool("set_antidetection", {"profile": "balanced"})

        data = get_mcp_result_data(result)

        assert data["status"] == "configured"
        assert data["profile"] == "balanced"
        assert "profile_info" in data

    @pytest.mark.asyncio
    async def test_set_stealth_profile(self):
        """Test setting stealth profile via MCP tool."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool("set_antidetection", {"profile": "stealth"})

        data = get_mcp_result_data(result)
        assert data["status"] == "configured"
        assert data["profile"] == "stealth"

        # Verify state was updated
        state = get_scraping_state()
        assert state.antidetection_profile == AntiDetectionProfile.STEALTH

    @pytest.mark.asyncio
    async def test_set_none_profile(self):
        """Test setting none profile via MCP tool."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool("set_antidetection", {"profile": "none"})

        data = get_mcp_result_data(result)
        assert data["status"] == "configured"
        assert data["profile"] == "none"

    @pytest.mark.asyncio
    async def test_set_browser_tls_profile(self):
        """Test setting browser_tls profile via MCP tool."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool("set_antidetection", {"profile": "browser_tls"})

        data = get_mcp_result_data(result)
        assert data["status"] == "configured"
        assert data["profile"] == "browser_tls"

        # Verify state was updated
        state = get_scraping_state()
        assert state.antidetection_profile == AntiDetectionProfile.BROWSER_TLS

    @pytest.mark.asyncio
    async def test_set_custom_profile_with_headers(self):
        """Test setting custom profile with custom headers."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool(
            "set_antidetection",
            {
                "profile": "custom",
                "custom_headers": {"X-Custom": "value"},
                "custom_user_agent": "TestBot/1.0",
            },
        )

        data = get_mcp_result_data(result)
        assert data["status"] == "configured"
        assert data["profile"] == "custom"
        assert data["custom_headers"] == {"X-Custom": "value"}
        assert data["custom_user_agent"] == "TestBot/1.0"

        # Verify state was updated
        state = get_scraping_state()
        assert state.custom_headers == {"X-Custom": "value"}
        assert state.custom_user_agent == "TestBot/1.0"

    @pytest.mark.asyncio
    async def test_invalid_profile_returns_error(self):
        """Test that invalid profile returns error."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool("set_antidetection", {"profile": "invalid"})

        data = get_mcp_result_data(result)
        assert data["success"] is False
        assert data["error_code"] == "INVALID_PROFILE"
        assert "recovery_strategy" in data
        assert "valid_profiles" in data.get("details", {})

    @pytest.mark.asyncio
    async def test_robots_txt_is_always_enabled(self):
        """robots.txt remains enabled regardless of provided input."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool(
            "set_antidetection",
            {"profile": "balanced", "respect_robots_txt": False},
        )

        data = get_mcp_result_data(result)
        assert data["respect_robots_txt"] is True

        state = get_scraping_state()
        assert state.respect_robots_txt is True

    @pytest.mark.asyncio
    async def test_set_rate_limit_delay(self):
        """Test setting rate_limit_delay option."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool(
            "set_antidetection",
            {"profile": "balanced", "rate_limit_delay": 2.5},
        )

        data = get_mcp_result_data(result)
        assert data["rate_limit_delay"] == 2.5

        state = get_scraping_state()
        assert state.rate_limit_delay == 2.5

    @pytest.mark.asyncio
    async def test_negative_rate_limit_returns_error(self):
        """Test that negative rate_limit_delay returns error."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool(
            "set_antidetection",
            {"profile": "balanced", "rate_limit_delay": -1},
        )

        data = get_mcp_result_data(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_set_max_response_chars(self):
        """Test setting max_response_chars option."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool(
            "set_antidetection",
            {"profile": "balanced", "max_response_chars": 50000},
        )

        data = get_mcp_result_data(result)
        assert data["max_response_chars"] == 50000

        state = get_scraping_state()
        assert state.max_response_chars == 50000

    @pytest.mark.asyncio
    async def test_max_response_chars_too_low_returns_error(self):
        """Test that max_response_chars below 4000 returns error."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool(
            "set_antidetection",
            {"profile": "balanced", "max_response_chars": 500},
        )

        data = get_mcp_result_data(result)
        assert data["success"] is False
        assert data["error_code"] == "INVALID_MAX_RESPONSE_CHARS"

    @pytest.mark.asyncio
    async def test_max_response_chars_too_high_returns_error(self):
        """Test that max_response_chars above 4000000 returns error."""
        from app.mcp_server.mcp_server import handle_call_tool

        result = await handle_call_tool(
            "set_antidetection",
            {"profile": "balanced", "max_response_chars": 5000000},
        )

        data = get_mcp_result_data(result)
        assert data["success"] is False
        assert data["error_code"] == "INVALID_MAX_RESPONSE_CHARS"

    @pytest.mark.asyncio
    async def test_tool_is_listed(self):
        """Test that set_antidetection tool is listed."""
        from app.mcp_server.mcp_server import handle_list_tools

        tools = await handle_list_tools()  # type: ignore[call-arg]
        tool_names = [t.name for t in tools]

        assert "set_antidetection" in tool_names

    @pytest.mark.asyncio
    async def test_tool_schema_has_required_profile(self):
        """Test that tool schema requires profile parameter."""
        from app.mcp_server.mcp_server import handle_list_tools

        tools = await handle_list_tools()  # type: ignore[call-arg]
        antidetection_tool = next(t for t in tools if t.name == "set_antidetection")

        assert "profile" in antidetection_tool.inputSchema.get("required", [])
