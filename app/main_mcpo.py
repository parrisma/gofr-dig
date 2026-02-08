#!/usr/bin/env python3
"""MCPO wrapper entry point for GOFR-DIG MCP server

This script starts an MCPO proxy that exposes the GOFR-DIG MCP server
as OpenAPI-compatible HTTP endpoints for Open WebUI integration.
"""

import argparse
import os
import signal
import sys

from app.logger import Logger, session_logger
from app.mcpo.wrapper import start_mcpo_wrapper

logger: Logger = session_logger


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info("Received shutdown signal", signal=signum)
    sys.exit(0)


if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="GOFR-DIG MCPO Wrapper - Expose MCP server as OpenAPI endpoints"
    )
    parser.add_argument(
        "--mcp-host",
        type=str,
        default="localhost",
        help="Host where MCP server is running (default: localhost)",
    )
    parser.add_argument(
        "--mcp-port",
        type=int,
        default=int(os.environ.get("GOFR_DIG_MCP_PORT", "8070")),
        help="Port where MCP server is listening (default: 8070)",
    )
    parser.add_argument(
        "--mcpo-port",
        type=int,
        default=int(os.environ.get("GOFR_DIG_MCPO_PORT", "8071")),
        help="Port for MCPO proxy to listen on (default: 8071)",
    )
    parser.add_argument(
        "--mcpo-host",
        type=str,
        default=os.environ.get("GOFR_DIG_MCPO_HOST", "0.0.0.0"),
        help="Host for MCPO proxy to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key for Open WebUI -> MCPO authentication (default: from GOFR_DIG_MCPO_API_KEY env or 'changeme')",
    )
    parser.add_argument(
        "--auth-token",
        type=str,
        default=None,
        help="JWT token for MCPO -> MCP authentication (default: from GOFR_DIG_JWT_TOKEN env)",
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Enable authenticated mode (requires --auth-token or GOFR_DIG_JWT_TOKEN)",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication (public mode, default)",
    )

    args = parser.parse_args()

    # Determine auth mode
    use_auth = False
    if args.auth:
        use_auth = True
    elif args.no_auth:
        use_auth = False
    else:
        # Check environment variable
        mode = os.environ.get("GOFR_DIG_MCPO_MODE", "public").lower()
        use_auth = mode == "auth"

    # Validate auth requirements
    auth_token = args.auth_token or os.environ.get("GOFR_DIG_JWT_TOKEN")
    if use_auth and not auth_token:
        logger.error("ERROR: --auth-token or GOFR_DIG_JWT_TOKEN required for authenticated mode")
        sys.exit(1)

    mode_str = "AUTHENTICATED" if use_auth else "PUBLIC (NO AUTH)"

    # Startup banner
    logger.info("=" * 70)
    logger.info("STARTING GOFR-DIG MCPO WRAPPER (OpenAPI Proxy)")
    logger.info("=" * 70)
    logger.info(
        "Configuration",
        mode=mode_str,
        mcp_endpoint=f"http://{args.mcp_host}:{args.mcp_port}/mcp",
        mcpo_bind=f"{args.mcpo_host}:{args.mcpo_port}",
        has_auth_token=bool(auth_token),
        has_api_key=bool(args.api_key),
    )
    logger.info("=" * 70)

    wrapper = None
    try:
        wrapper = start_mcpo_wrapper(
            mcp_host=args.mcp_host,
            mcp_port=args.mcp_port,
            mcpo_port=args.mcpo_port,
            mcpo_host=args.mcpo_host,
            mcpo_api_key=args.api_key,
            auth_token=auth_token,
            use_auth=use_auth,
        )

        if wrapper and wrapper.process:
            logger.info("MCPO wrapper started successfully")
            logger.info(f"OpenAPI endpoint: http://{args.mcpo_host}:{args.mcpo_port}")
            logger.info(f"Documentation: http://{args.mcpo_host}:{args.mcpo_port}/docs")
            logger.info("=" * 70)

            # Wait for process to complete (or be interrupted)
            wrapper.process.wait()
        else:
            logger.error(
                "Failed to start MCPO wrapper",
                reason="wrapper process not created",
                host=args.mcpo_host,
                port=args.mcpo_port,
            )
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Shutting down MCPO wrapper...")
    except Exception as e:
        logger.error("MCPO wrapper error", error=str(e), error_type=type(e).__name__)
        sys.exit(1)
    finally:
        if wrapper:
            wrapper.stop()
        logger.info("=" * 70)
        logger.info("MCPO wrapper shutdown complete")
        logger.info("=" * 70)
