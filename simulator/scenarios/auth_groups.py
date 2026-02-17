from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.logger import Logger, session_logger
from mcp import ClientSession
from mcp.client import streamable_http

from simulator.core.auth import TokenFactory
from simulator.fixtures.html_fixture_server import HTMLFixtureServer


streamable_http_client = streamable_http.streamablehttp_client


@dataclass(frozen=True)
class AuthGroupsResult:
    session_apac: str
    session_emea: str
    session_us: str


def _parse_payload(result) -> dict[str, Any]:
    if not result.content:
        return {"success": False, "error": "empty_response"}
    text = getattr(result.content[0], "text", None)
    if not isinstance(text, str):
        return {"success": False, "error": "non_text_response"}
    try:
        return json.loads(text)
    except Exception:
        return {"success": False, "error": "non_json_response"}


async def run_auth_groups_scenario(
    *,
    mcp_url: str,
    fixtures_dir: str,
    logger: Logger | None = None,
) -> AuthGroupsResult:
    """Create sessions in apac/emea/us and validate cross-group reads.

    Assertions:
    - token_multi can read session info for apac/emea/us sessions
    - token_emea cannot read apac session

    Uses local HTML fixtures for deterministic pages.
    """

    log = logger or session_logger

    token_set = TokenFactory(logger=log).mint_required_tokens(expires_in_seconds=3600)

    with HTMLFixtureServer(fixtures_dir=fixtures_dir, logger=log) as fixture_server:
        url_apac = fixture_server.get_url("index.html")
        url_emea = fixture_server.get_url("products.html")
        url_us = fixture_server.get_url("product-detail.html")

        async with streamable_http_client(mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Create sessions (ownership = primary group)
                apac_payload = _parse_payload(
                    await session.call_tool(
                        "get_content",
                        {
                            "url": url_apac,
                            "parse_results": False,
                            "session": True,
                            "auth_token": token_set.token_apac,
                        },
                    )
                )
                emea_payload = _parse_payload(
                    await session.call_tool(
                        "get_content",
                        {
                            "url": url_emea,
                            "parse_results": False,
                            "session": True,
                            "auth_token": token_set.token_emea,
                        },
                    )
                )
                us_payload = _parse_payload(
                    await session.call_tool(
                        "get_content",
                        {
                            "url": url_us,
                            "parse_results": False,
                            "session": True,
                            "auth_token": token_set.token_us,
                        },
                    )
                )

                for name, payload in (
                    ("apac", apac_payload),
                    ("emea", emea_payload),
                    ("us", us_payload),
                ):
                    if payload.get("success") is not True or not payload.get("session_id"):
                        raise RuntimeError(f"failed to create {name} session: {payload}")

                session_apac = str(apac_payload["session_id"])
                session_emea = str(emea_payload["session_id"])
                session_us = str(us_payload["session_id"])

                # Cross-group read with multi token (should succeed)
                for sid in (session_apac, session_emea, session_us):
                    info_payload = _parse_payload(
                        await session.call_tool(
                            "get_session_info",
                            {"session_id": sid, "auth_token": token_set.token_multi},
                        )
                    )
                    if not info_payload.get("session_id"):
                        raise RuntimeError(f"token_multi could not read session {sid}: {info_payload}")

                # Negative check: wrong single-group token should be denied
                denied_payload = _parse_payload(
                    await session.call_tool(
                        "get_session_info",
                        {"session_id": session_apac, "auth_token": token_set.token_emea},
                    )
                )
                if denied_payload.get("success") is not False or denied_payload.get("error_code") != "PERMISSION_DENIED":
                    raise RuntimeError(f"expected PERMISSION_DENIED, got: {denied_payload}")

                log.info(
                    "sim.auth_groups_ok",
                    event="sim.auth_groups_ok",
                    session_apac=session_apac,
                    session_emea=session_emea,
                    session_us=session_us,
                )

                return AuthGroupsResult(
                    session_apac=session_apac,
                    session_emea=session_emea,
                    session_us=session_us,
                )
