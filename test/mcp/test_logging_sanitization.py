"""Tests for MCP logging sanitization behavior."""

import pytest

from app.mcp_server import mcp_server


class _CaptureLogger:
    def __init__(self):
        self.info_calls = []
        self.warning_calls = []

    def info(self, message: str, **kwargs):
        self.info_calls.append((message, kwargs))

    def warning(self, message: str, **kwargs):
        self.warning_calls.append((message, kwargs))


@pytest.mark.asyncio
async def test_tool_invocation_logs_are_sanitized(monkeypatch):
    fake_logger = _CaptureLogger()
    monkeypatch.setattr(mcp_server, "logger", fake_logger)

    await mcp_server.handle_call_tool(
        "ping",
        {
            "auth_token": "Bearer should-not-be-logged",
            "Authorization": "Bearer should-not-be-logged",
            "url": "https://example.com/private/path",
            "selector": "#main",
            "depth": 2,
            "session": True,
        },
    )

    invoke_events = [
        payload for message, payload in fake_logger.info_calls if payload.get("event") == "tool_invoked"
    ]
    complete_events = [
        payload for message, payload in fake_logger.info_calls if payload.get("event") == "tool_completed"
    ]

    assert invoke_events, "Expected tool_invoked log event"
    assert complete_events, "Expected tool_completed log event"

    invoke_payload = invoke_events[0]
    assert invoke_payload.get("tool") == "ping"
    assert invoke_payload.get("selector_present") is True
    assert invoke_payload.get("depth") == 2
    assert invoke_payload.get("session_mode") is True
    assert invoke_payload.get("url_host") == "example.com"
    assert "args" not in invoke_payload
    assert "auth_token" not in invoke_payload
    assert "Authorization" not in invoke_payload
