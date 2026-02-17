from __future__ import annotations

import asyncio
import signal
import time

from app.logger import Logger, session_logger

from simulator.core.consumer import Consumer, ConsumerConfig, Counters, RequestBudget
from simulator.core.metrics import MetricsCollector
from simulator.core.models import SimulationConfig, SimulationResult
from simulator.core.models import Mode
from simulator.core.provider import SiteProvider, URLListProvider, build_fixture_urls
from simulator.fixtures.html_fixture_server import HTMLFixtureServer


class Simulator:
    def __init__(
        self,
        config: SimulationConfig,
        *,
        logger: Logger | None = None,
        mix_file: str | None = None,
        token_source: str = "auto",
        fixtures_dir: str | None = None,
    ) -> None:
        self._config = config
        self._logger = logger or session_logger
        self._mix_file = mix_file
        self._token_source = token_source
        self._fixtures_dir = fixtures_dir

    async def run(self) -> SimulationResult:
        if self._config.consumers < 1 and not self._mix_file:
            raise ValueError("consumers must be >= 1 (or provide --mix-file)")

        if self._config.total_requests is None and self._config.duration_seconds is None:
            raise ValueError("one of total_requests or duration_seconds must be provided")

        fixture_server: HTMLFixtureServer | None = None
        if self._config.mode == Mode.FIXTURE:
            fixtures_dir = self._fixtures_dir
            if not fixtures_dir:
                raise ValueError("fixtures_dir must be provided for fixture mode")

            fixture_server = HTMLFixtureServer(fixtures_dir=fixtures_dir, logger=self._logger)
            fixture_server.start()
            urls = build_fixture_urls(fixture_server.base_url, fixtures_dir)
            provider = URLListProvider(urls)
        elif self._config.target_url:
            provider = _StaticSiteProvider(self._config.target_url)
        else:
            provider = SiteProvider.load_from_file(self._config.sites_file)

        stop_event = asyncio.Event()
        counters = Counters()
        budget = RequestBudget(self._config.total_requests)
        metrics = MetricsCollector(logger=self._logger)

        started = time.monotonic()

        consumer_configs = self._build_consumer_configs()
        consumer_count = len(consumer_configs)

        self._logger.info(
            "sim.start",
            event="sim.start",
            mode=self._config.mode.value,
            consumers=consumer_count,
            rate_per_consumer_per_sec=self._config.rate_per_consumer_per_sec,
            total_requests=self._config.total_requests,
            duration_seconds=self._config.duration_seconds,
            mcp_url=self._config.mcp_url,
            mix_file=self._mix_file,
            token_source=self._token_source,
        )

        def _handle_signal(signum: int, _frame) -> None:  # pragma: no cover
            self._logger.warning("sim.signal", event="sim.signal", signum=signum)
            stop_event.set()

        try:
            with _SignalHandlers(_handle_signal):
                tasks: list[asyncio.Task[None]] = []
                consumers: list[Consumer] = []

                for consumer_cfg in consumer_configs:
                    consumer = Consumer(
                        consumer_cfg,
                        provider,
                        logger=self._logger,
                        metrics=metrics,
                    )
                    consumers.append(consumer)

                    tasks.append(
                        asyncio.create_task(
                            consumer.run(
                                stop_event=stop_event,
                                request_budget=budget,
                                counters=counters,
                            )
                        )
                    )

                # Optional time-based stop.
                if self._config.duration_seconds is not None:
                    tasks.append(
                        asyncio.create_task(
                            _stop_after(stop_event, self._config.duration_seconds)
                        )
                    )

                try:
                    await asyncio.gather(*tasks)
                finally:
                    for consumer in consumers:
                        await consumer.aclose()
        finally:
            if fixture_server is not None:
                fixture_server.stop()

        ended = time.monotonic()
        ok, error = counters.snapshot()

        metrics_report = await metrics.build_report()

        result = SimulationResult(
            started_at_monotonic=started,
            ended_at_monotonic=ended,
            request_count=ok + error,
            error_count=error,
            metrics_report=metrics_report,
        )

        self._logger.info(
            "sim.end",
            event="sim.end",
            request_count=result.request_count,
            error_count=result.error_count,
            duration_seconds=result.duration_seconds,
            throughput_rps=result.throughput_rps,
        )

        return result

    def _build_consumer_configs(self) -> list[ConsumerConfig]:
        if not self._mix_file:
            return [
                ConsumerConfig(
                    consumer_id=i,
                    rate_per_sec=self._config.rate_per_consumer_per_sec,
                    timeout_seconds=self._config.timeout_seconds,
                    mcp_url=self._config.mcp_url,
                    persona=None,
                )
                for i in range(self._config.consumers)
            ]

        from simulator.core.mix import load_mix_file

        mix = load_mix_file(self._mix_file)
        tokens = self._resolve_tokens_for_mix(mix) if self._config.mcp_url else {}

        configs: list[ConsumerConfig] = []
        consumer_id = 0
        for entry in mix.entries:
            auth_token = None
            if not self._config.mcp_url:
                # Direct HTTP mode doesn't use auth tokens.
                auth_token = None
            elif entry.token is None:
                auth_token = None
            else:
                auth_token = tokens.get(entry.token, entry.token)

            for _ in range(entry.count):
                configs.append(
                    ConsumerConfig(
                        consumer_id=consumer_id,
                        rate_per_sec=self._config.rate_per_consumer_per_sec,
                        timeout_seconds=self._config.timeout_seconds,
                        mcp_url=self._config.mcp_url,
                        auth_token=auth_token,
                        persona=entry.name,
                    )
                )
                consumer_id += 1

        if self._config.consumers not in (0, len(configs)):
            self._logger.warning(
                "sim.mix_overrides_consumers",
                event="sim.mix_overrides_consumers",
                consumers_arg=self._config.consumers,
                consumers_from_mix=len(configs),
            )

        return configs

    def _resolve_tokens_for_mix(self, mix) -> dict[str, str]:
        """Resolve symbolic tokens used in the mix file.

        Returns mapping for symbolic token names (e.g. "token_apac") to concrete JWT strings.
        Literal JWT strings are passed through without mapping.
        """

        symbolic = {e.token for e in mix.entries if isinstance(e.token, str) and e.token.startswith("token_")}
        if not symbolic:
            return {}

        # Always provide invalid token mapping.
        resolved: dict[str, str] = {"token_invalid": "invalid.invalid.invalid"}

        if self._token_source in ("auto", "env"):
            from simulator.core.auth import tokens_from_env

            env_tokens = tokens_from_env("GOFR_DIG")
            if "apac" in env_tokens:
                resolved["token_apac"] = env_tokens["apac"]
            if "emea" in env_tokens:
                resolved["token_emea"] = env_tokens["emea"]
            if "us" in env_tokens:
                resolved["token_us"] = env_tokens["us"]
            if "multi" in env_tokens:
                resolved["token_multi"] = env_tokens["multi"]

        missing = [
            name
            for name in ("token_apac", "token_emea", "token_us", "token_multi")
            if name in symbolic and name not in resolved
        ]

        if missing and self._token_source in ("auto", "mint"):
            try:
                from simulator.core.auth import TokenFactory

                token_set = TokenFactory(logger=self._logger).mint_required_tokens()
                resolved.setdefault("token_apac", token_set.token_apac)
                resolved.setdefault("token_emea", token_set.token_emea)
                resolved.setdefault("token_us", token_set.token_us)
                resolved.setdefault("token_multi", token_set.token_multi)
                resolved.setdefault("token_expired", token_set.token_expired)
            except Exception as exc:
                self._logger.error(
                    "sim.token_mint_failed",
                    event="sim.token_mint_failed",
                    error_type=type(exc).__name__,
                    error=str(exc),
                    recovery="Set GOFR_DIG_SIM_TOKEN_* env vars or run with --token-source env",
                )

        # If we still can't resolve required symbolic tokens, fail fast.
        missing_after = [
            name
            for name in ("token_apac", "token_emea", "token_us", "token_multi")
            if name in symbolic and name not in resolved
        ]
        if missing_after:
            raise ValueError(
                "Missing required tokens for mix: " + ", ".join(missing_after)
            )

        return resolved


class _StaticSiteProvider:
    def __init__(self, url: str) -> None:
        self._url = url

    def choose_url(self) -> str:
        return self._url


async def _stop_after(stop_event: asyncio.Event, duration_seconds: float) -> None:
    await asyncio.sleep(max(0.0, duration_seconds))
    stop_event.set()


class _SignalHandlers:
    def __init__(self, handler) -> None:
        self._handler = handler
        self._previous: dict[int, object] = {}

    def __enter__(self):
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                self._previous[signum] = signal.signal(signum, self._handler)
            except Exception:
                # Some platforms/restrictions may forbid signal handling.
                pass
        return self

    def __exit__(self, exc_type, exc, tb):
        for signum, previous in self._previous.items():
            try:
                signal.signal(signum, previous)  # type: ignore[arg-type]
            except Exception:
                pass
        return False
