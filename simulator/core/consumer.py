from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.logger import Logger, session_logger

# Retry / back-off constants for 429 and transient server errors.
_RETRY_STATUS_CODES = frozenset({429, 502, 503, 504})
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 30.0


class URLProvider(Protocol):
    def choose_url(self) -> str: ...


@dataclass(frozen=True)
class ConsumerConfig:
    consumer_id: int
    rate_per_sec: float
    timeout_seconds: float
    mcp_url: str | None = None
    auth_token: str | None = None
    persona: str | None = None
    max_retries: int = _MAX_RETRIES
    backoff_base: float = _BACKOFF_BASE_SECONDS
    backoff_max: float = _BACKOFF_MAX_SECONDS


class Consumer:
    """A single concurrent consumer.

    Phase 1 behavior: plain HTTP GET to URLs from SiteProvider.
    Later phases: MCP tool mix, auth personas, sessions, fixtures.
    """

    def __init__(
        self,
        config: ConsumerConfig,
        provider: URLProvider,
        *,
        logger: Logger | None = None,
        metrics: "MetricsCollector | None" = None,
    ) -> None:
        if config.rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")

        self._config = config
        self._provider = provider
        self._logger = logger or session_logger
        self._metrics = metrics

        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=True,
            headers={
                "User-Agent": "gofr-dig-simulator/0.1",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def run(
        self,
        *,
        stop_event: asyncio.Event,
        request_budget: "RequestBudget",
        counters: "Counters",
    ) -> None:
        interval = 1.0 / self._config.rate_per_sec
        next_fire = time.monotonic()

        if self._config.mcp_url:
            await self._run_mcp(stop_event=stop_event, request_budget=request_budget, counters=counters)
            return

        while not stop_event.is_set():
            if not await request_budget.try_acquire():
                stop_event.set()
                break

            now = time.monotonic()
            if now < next_fire:
                await asyncio.sleep(next_fire - now)
            next_fire = max(next_fire + interval, time.monotonic())

            url = self._provider.choose_url()
            start = time.monotonic()

            try:
                response = await self._request_with_retry(url)
                duration_ms = int((time.monotonic() - start) * 1000)

                error_type = _classify_http_error(response.status_code)
                ok = error_type is None

                if self._metrics is not None:
                    await self._metrics.record(
                        tool_name="http.get",
                        duration_ms=duration_ms,
                        success=ok,
                        persona=self._config.persona,
                        error_type=error_type,
                    )

                if ok:
                    await counters.record_ok()
                    self._logger.info(
                        "sim.consumer_request_ok",
                        event="sim.consumer_request_ok",
                        consumer_id=self._config.consumer_id,
                        url=url,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                    )
                else:
                    await counters.record_error()
                    self._logger.warning(
                        "sim.consumer_request_error",
                        event="sim.consumer_request_error",
                        consumer_id=self._config.consumer_id,
                        url=url,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        error_type=error_type,
                    )
            except Exception as exc:
                duration_ms = int((time.monotonic() - start) * 1000)

                if self._metrics is not None:
                    await self._metrics.record(
                        tool_name="http.get",
                        duration_ms=duration_ms,
                        success=False,
                        persona=self._config.persona,
                        error_type=_classify_exception(exc),
                    )

                await counters.record_error()
                self._logger.warning(
                    "sim.consumer_request_error",
                    event="sim.consumer_request_error",
                    consumer_id=self._config.consumer_id,
                    url=url,
                    duration_ms=duration_ms,
                    error_type=_classify_exception(exc),
                    error=str(exc),
                )

    async def _request_with_retry(self, url: str) -> httpx.Response:
        """HTTP GET with exponential back-off on retryable status codes (429, 5xx)."""
        last_response: httpx.Response | None = None
        for attempt in range(1 + self._config.max_retries):
            resp = await self._http.get(url)
            if resp.status_code not in _RETRY_STATUS_CODES or attempt == self._config.max_retries:
                return resp
            last_response = resp

            delay = _backoff_delay(
                attempt,
                base=self._config.backoff_base,
                cap=self._config.backoff_max,
                retry_after=resp.headers.get("Retry-After"),
            )
            self._logger.info(
                "sim.consumer_retry",
                event="sim.consumer_retry",
                consumer_id=self._config.consumer_id,
                url=url,
                status_code=resp.status_code,
                attempt=attempt + 1,
                delay_seconds=round(delay, 2),
            )
            await asyncio.sleep(delay)

        # Should not be reachable, but satisfy the type-checker.
        assert last_response is not None  # pragma: no cover
        return last_response  # pragma: no cover

    async def _run_mcp(
        self,
        *,
        stop_event: asyncio.Event,
        request_budget: "RequestBudget",
        counters: "Counters",
    ) -> None:
        import json

        from mcp import ClientSession
        from mcp.client import streamable_http

        assert self._config.mcp_url is not None
        interval = 1.0 / self._config.rate_per_sec
        next_fire = time.monotonic()

        def _parse_payload(result) -> dict:
            if not result.content:
                return {"success": False, "error": "empty_response"}
            text = getattr(result.content[0], "text", None)
            if not isinstance(text, str):
                return {"success": False, "error": "non_text_response"}
            try:
                return json.loads(text)
            except Exception:
                return {"success": False, "error": "non_json_response"}

        def _mcp_error_type(payload: dict) -> str:
            """Extract a canonical error_type from an MCP tool response payload."""
            code = payload.get("error_code") or payload.get("error") or ""
            code_str = str(code).lower()
            if "auth" in code_str or "token" in code_str or "unauthorized" in code_str:
                return "auth_error"
            if "rate" in code_str or "429" in code_str or "throttl" in code_str:
                return "rate_limited"
            if "timeout" in code_str:
                return "network_timeout"
            if "fetch" in code_str or "network" in code_str or "connect" in code_str:
                return "network_error"
            return "mcp_tool_failed"

        streamable_http_client = streamable_http.streamablehttp_client

        async def _timed_call(tool_name: str, arguments: dict[str, object]) -> tuple[dict, bool, int]:
            tool_start = time.monotonic()
            try:
                raw = await session.call_tool(tool_name, arguments)
                payload = _parse_payload(raw)
                ok = bool(payload.get("success", True))
                return payload, ok, int((time.monotonic() - tool_start) * 1000)
            except Exception as exc:
                payload = {"success": False, "error": str(exc)}
                return payload, False, int((time.monotonic() - tool_start) * 1000)

        try:
            async with streamable_http_client(self._config.mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # Basic connectivity signal.
                    await session.call_tool("ping", {})

                    while not stop_event.is_set():
                        if not await request_budget.try_acquire():
                            stop_event.set()
                            break

                        now = time.monotonic()
                        if now < next_fire:
                            await asyncio.sleep(next_fire - now)
                        next_fire = max(next_fire + interval, time.monotonic())

                        url = self._provider.choose_url()
                        start = time.monotonic()

                        # Step 1: structure
                        structure_args: dict[str, object] = {"url": url}
                        if self._config.auth_token:
                            structure_args["auth_token"] = self._config.auth_token
                        structure_payload, structure_ok, structure_ms = await _timed_call(
                            "get_structure",
                            structure_args,
                        )
                        if self._metrics is not None:
                            await self._metrics.record(
                                tool_name="mcp.get_structure",
                                duration_ms=structure_ms,
                                success=structure_ok,
                                persona=self._config.persona,
                                error_type=None if structure_ok else _mcp_error_type(structure_payload),
                            )

                        # Step 2: content with session storage
                        content_args: dict[str, object] = {
                            "url": url,
                            "parse_results": False,
                            "session": True,
                        }
                        if self._config.auth_token:
                            content_args["auth_token"] = self._config.auth_token
                        content_payload, content_ok, content_ms = await _timed_call(
                            "get_content",
                            content_args,
                        )
                        if self._metrics is not None:
                            await self._metrics.record(
                                tool_name="mcp.get_content",
                                duration_ms=content_ms,
                                success=content_ok,
                                persona=self._config.persona,
                                error_type=None if content_ok else _mcp_error_type(content_payload),
                            )

                        # Step 3: session reads (if session created)
                        session_ok = False
                        session_id = content_payload.get("session_id")
                        if isinstance(session_id, str) and session_id:
                            session_ok = True

                        if session_ok:
                            info_args: dict[str, object] = {"session_id": session_id}
                            if self._config.auth_token:
                                info_args["auth_token"] = self._config.auth_token
                            info_payload, info_ok, info_ms = await _timed_call("get_session_info", info_args)
                            if self._metrics is not None:
                                await self._metrics.record(
                                    tool_name="mcp.get_session_info",
                                    duration_ms=info_ms,
                                    success=info_ok,
                                    persona=self._config.persona,
                                    error_type=None if info_ok else _mcp_error_type(info_payload),
                                )
                            # If session reads fail, treat session reads as failed for logging.
                            if not info_payload.get("success", True):
                                session_ok = False

                            chunk_args: dict[str, object] = {
                                "session_id": session_id,
                                "chunk_index": 0,
                            }
                            if self._config.auth_token:
                                chunk_args["auth_token"] = self._config.auth_token
                            chunk_payload, chunk_ok, chunk_ms = await _timed_call("get_session_chunk", chunk_args)
                            if self._metrics is not None:
                                await self._metrics.record(
                                    tool_name="mcp.get_session_chunk",
                                    duration_ms=chunk_ms,
                                    success=chunk_ok,
                                    persona=self._config.persona,
                                    error_type=None if chunk_ok else _mcp_error_type(chunk_payload),
                                )
                            if not chunk_payload.get("success", True):
                                session_ok = False

                        duration_ms = int((time.monotonic() - start) * 1000)

                        if structure_payload.get("success") is True and content_payload.get("success") is True:
                            await counters.record_ok()
                            self._logger.info(
                                "sim.consumer_mcp_ok",
                                event="sim.consumer_mcp_ok",
                                consumer_id=self._config.consumer_id,
                                url=url,
                                duration_ms=duration_ms,
                                did_structure=True,
                                did_content=True,
                                did_session_reads=session_ok,
                            )
                        else:
                            await counters.record_error()
                            self._logger.warning(
                                "sim.consumer_mcp_error",
                                event="sim.consumer_mcp_error",
                                consumer_id=self._config.consumer_id,
                                url=url,
                                duration_ms=duration_ms,
                                structure_ok=structure_payload.get("success"),
                                content_ok=content_payload.get("success"),
                                session_ok=session_ok,
                                structure_error=structure_payload.get("error") or structure_payload.get("message"),
                                content_error=content_payload.get("error") or content_payload.get("message"),
                            )
        except Exception as exc:
            await counters.record_error()
            self._logger.error(
                "sim.mcp_connection_failed",
                event="sim.mcp_connection_failed",
                consumer_id=self._config.consumer_id,
                mcp_url=self._config.mcp_url,
                error_type=type(exc).__name__,
                error=str(exc),
                recovery="Ensure the test Docker stack is running and the dev container is connected to gofr-test-net",
            )
            stop_event.set()


# ---------------------------------------------------------------------------
# Helpers: error classification and back-off
# ---------------------------------------------------------------------------

def _classify_http_error(status_code: int) -> str | None:
    """Map an HTTP status code to a canonical error_type, or None if success."""
    if 200 <= status_code < 400:
        return None
    if status_code == 401:
        return "auth_unauthorized"
    if status_code == 403:
        return "auth_forbidden"
    if status_code == 404:
        return "not_found"
    if status_code == 429:
        return "rate_limited"
    if 400 <= status_code < 500:
        return "client_error"
    if 500 <= status_code < 600:
        return "server_error"
    return f"http_{status_code}"


def _classify_exception(exc: Exception) -> str:
    """Map a network-level exception to a canonical error_type."""
    import httpx as _httpx

    if isinstance(exc, _httpx.TimeoutException):
        return "network_timeout"
    if isinstance(exc, _httpx.ConnectError):
        return "network_connect"
    if isinstance(exc, (_httpx.RemoteProtocolError, _httpx.LocalProtocolError)):
        return "network_protocol"
    if isinstance(exc, _httpx.HTTPError):
        return "network_error"
    return type(exc).__name__


def _backoff_delay(
    attempt: int,
    *,
    base: float = _BACKOFF_BASE_SECONDS,
    cap: float = _BACKOFF_MAX_SECONDS,
    retry_after: str | None = None,
) -> float:
    """Compute back-off delay, honouring Retry-After header when present."""
    if retry_after is not None:
        try:
            return min(float(retry_after), cap)
        except ValueError:
            pass
    return min(base * (2 ** attempt), cap)


from simulator.core.metrics import MetricsCollector  # noqa: E402  - avoid circular typing imports


class RequestBudget:
    """Shared request budget across all consumers."""

    def __init__(self, total_requests: int | None) -> None:
        self._remaining = total_requests
        self._lock = asyncio.Lock()

    def is_limited(self) -> bool:
        return self._remaining is not None

    def remaining(self) -> int | None:
        return self._remaining

    async def try_acquire(self) -> bool:
        """Return True if one request is acquired, False if budget is exhausted."""
        if self._remaining is None:
            return True

        async with self._lock:
            if self._remaining is None:
                return True
            if self._remaining <= 0:
                return False
            self._remaining -= 1
            return True


class Counters:
    def __init__(self) -> None:
        self.ok = 0
        self.error = 0
        self._lock = asyncio.Lock()

    def snapshot(self) -> tuple[int, int]:
        return self.ok, self.error

    async def record_ok(self) -> None:
        async with self._lock:
            self.ok += 1

    async def record_error(self) -> None:
        async with self._lock:
            self.error += 1
