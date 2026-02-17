from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from app.logger import session_logger as logger

from simulator.core.engine import Simulator
from simulator.core.models import Mode, SimulationConfig
from simulator.core.timeparse import parse_duration_to_seconds
from simulator.api.report import build_simulation_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="gofr-dig simulation harness")
    parser.add_argument(
        "--scenario",
        type=str,
        choices=["load", "auth-groups"],
        default="load",
        help="Scenario to run: load (default) or auth-groups",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=[m.value for m in Mode],
        default=Mode.LIVE.value,
        help="Simulation mode (live|fixture|record). record is added in later phases.",
    )
    parser.add_argument(
        "--consumers",
        type=int,
        default=None,
        help="Number of consumers (optional if --mix-file is set)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="Per-consumer request rate (requests/sec). Required for scenario=load.",
    )
    parser.add_argument(
        "--total-requests",
        type=int,
        default=None,
        help="Total requests across all consumers (optional if --duration is set)",
    )
    parser.add_argument(
        "--duration",
        type=str,
        default=None,
        help="Run duration (e.g. 30s, 5m). Optional if --total-requests is set.",
    )
    parser.add_argument(
        "--mcp-url",
        type=str,
        default=os.environ.get("GOFR_DIG_MCP_URL"),
        help="Optional MCP endpoint URL (e.g. http://gofr-dig-mcp:8070/mcp). If set, consumers call MCP tools instead of direct HTTP.",
    )
    parser.add_argument(
        "--mix-file",
        type=str,
        default=None,
        help="Path to a consumer mix JSON file (see simulator/mix.example.json)",
    )
    parser.add_argument(
        "--token-source",
        type=str,
        choices=["auto", "mint", "env"],
        default="auto",
        help="How to resolve symbolic tokens (token_apac/token_multi/etc): auto|mint|env",
    )
    parser.add_argument(
        "--sites-file",
        type=str,
        default=str(Path(__file__).with_name("sites.json")),
        help="Path to sites.json",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=str,
        default=str(Path(__file__).parent.parent / "test" / "fixtures" / "html"),
        help="Directory containing HTML fixtures (used with --mode fixture)",
    )
    parser.add_argument(
        "--target-url",
        type=str,
        default=None,
        help="Optional single URL override (Phase 1: not yet used for selection)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="HTTP timeout per request",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write summary report JSON to this path",
    )
    parser.add_argument(
        "--record-output-dir",
        type=str,
        default=str(Path(__file__).parent / "fixtures" / "data"),
        help="Directory to write recorded fixtures (used with --mode record)",
    )
    return parser


def _run_record_mode(args) -> int:
    """Record live sites to obfuscated fixtures."""
    from simulator.core.provider import SiteProvider
    from simulator.fixtures.storage import FixtureStore
    from simulator.recording.recorder import Recorder

    provider = SiteProvider.load_from_file(args.sites_file)
    urls = [site.url for site in provider._sites]

    if not urls:
        logger.error(
            "sim.record_no_urls",
            event="sim.record_no_urls",
            sites_file=args.sites_file,
            recovery="Ensure sites.json contains at least one URL",
        )
        return 2

    store = FixtureStore(args.record_output_dir)
    recorder = Recorder(
        store=store,
        timeout_seconds=args.timeout_seconds,
        logger=logger,
    )

    async def _record() -> int:
        result = await recorder.record_urls(urls)
        logger.info(
            "sim.record_summary",
            event="sim.record_summary",
            sites_attempted=result.sites_attempted,
            sites_recorded=result.sites_recorded,
            sites_failed=result.sites_failed,
            total_bytes=result.total_bytes,
            output_dir=args.record_output_dir,
        )
        if result.sites_recorded == 0:
            logger.error(
                "sim.record_all_failed",
                event="sim.record_all_failed",
                recovery="Check network connectivity and sites.json URLs",
            )
            return 1
        return 0

    return asyncio.run(_record())


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.mode == Mode.RECORD.value:
        return _run_record_mode(args)

    if args.scenario == "load" and args.rate <= 0:
        logger.error(
            "sim.invalid_rate",
            event="sim.invalid_rate",
            provided=args.rate,
            recovery="Provide --rate > 0",
        )
        return 2

    duration_seconds = None
    if args.duration is not None:
        try:
            duration_seconds = parse_duration_to_seconds(args.duration)
        except Exception as exc:
            logger.error(
                "sim.invalid_duration",
                event="sim.invalid_duration",
                provided=args.duration,
                error=str(exc),
            )
            return 2

    if args.scenario == "load" and args.total_requests is None and duration_seconds is None:
        logger.error(
            "sim.missing_stop_condition",
            event="sim.missing_stop_condition",
            cause="total_requests_and_duration_both_missing",
            recovery="Provide --total-requests or --duration",
        )
        return 2

    # Scenario: auth-groups
    if args.scenario == "auth-groups":
        if not args.mcp_url:
            logger.error(
                "sim.missing_mcp_url",
                event="sim.missing_mcp_url",
                recovery="Provide --mcp-url for auth-groups scenario",
            )
            return 2

        from simulator.scenarios.auth_groups import run_auth_groups_scenario

        async def _run() -> int:
            await run_auth_groups_scenario(
                mcp_url=args.mcp_url,
                fixtures_dir=args.fixtures_dir,
                logger=logger,
            )
            return 0

        return asyncio.run(_run())

    # Resolve consumer count (load only)
    mix_file = args.mix_file.strip() if args.mix_file else None
    if args.scenario == "load" and args.consumers is None and mix_file is None:
        logger.error(
            "sim.missing_consumers",
            event="sim.missing_consumers",
            recovery="Provide --consumers or --mix-file",
        )
        return 2

    consumers = int(args.consumers) if args.consumers is not None else 0

    config = SimulationConfig(
        mode=Mode(args.mode),
        consumers=consumers,
        rate_per_consumer_per_sec=args.rate,
        total_requests=args.total_requests,
        duration_seconds=duration_seconds,
        mcp_url=(args.mcp_url.strip() if args.mcp_url else None),
        sites_file=args.sites_file,
        target_url=args.target_url,
        timeout_seconds=args.timeout_seconds,
    )

    simulator = Simulator(
        config,
        logger=logger,
        mix_file=mix_file,
        token_source=args.token_source,
        fixtures_dir=(args.fixtures_dir.strip() if args.fixtures_dir else None),
    )
    result = asyncio.run(simulator.run())

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = build_simulation_report(config, result)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

        logger.info(
            "sim.report_written",
            event="sim.report_written",
            path=str(output_path),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
