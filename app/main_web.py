"""GOFR-DIG Web Server entry point - Minimal stub implementation."""

import uvicorn
import argparse
import os
import sys

from app.web_server.web_server import GofrDigWebServer
from app.auth import AuthService
from app.logger import Logger, session_logger
import app.startup.validation
from app.startup.auth_config import resolve_auth_config

logger: Logger = session_logger

if __name__ == "__main__":
    # Validate data directory structure at startup
    try:
        app.startup.validation.validate_data_directory_structure(logger)
    except RuntimeError as e:
        logger.error("FATAL: Data directory validation failed", error=str(e))
        sys.exit(1)

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="GOFR-DIG Web Server - Stub REST API")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host address to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("GOFR_DIG_WEB_PORT", "8032")),
        help="Port number to listen on (default: 8032, or GOFR_DIG_WEB_PORT env var)",
    )
    parser.add_argument(
        "--jwt-secret",
        type=str,
        default=None,
        help="JWT secret key (default: from GOFR_DIG_JWT_SECRET env var or auto-generated)",
    )
    parser.add_argument(
        "--token-store",
        type=str,
        default=None,
        help="Path to token store file (default: configured in app.config)",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication (WARNING: insecure, for development only)",
    )
    args = parser.parse_args()

    # Validate JWT secret if authentication is enabled
    jwt_secret, token_store_path = resolve_auth_config(
        jwt_secret_arg=args.jwt_secret,
        token_store_arg=args.token_store,
        require_auth=not args.no_auth,
        logger=logger,
    )

    # Initialize AuthService if authentication is enabled
    auth_service = None
    if jwt_secret:
        auth_service = AuthService(secret_key=jwt_secret, token_store_path=token_store_path)
        logger.info(
            "Authentication service initialized",
            jwt_enabled=True,
            token_store=token_store_path,
        )
    else:
        logger.warning(
            "Authentication DISABLED - running in no-auth mode (INSECURE)",
            jwt_enabled=False,
        )

    # Initialize server
    server = GofrDigWebServer(
        auth_service=auth_service,
        host=args.host,
        port=args.port,
    )

    try:
        logger.info("=" * 70)
        logger.info("STARTING GOFR-DIG WEB SERVER (STUB)")
        logger.info("=" * 70)
        logger.info(
            "Configuration",
            host=args.host,
            port=args.port,
            jwt_enabled=not args.no_auth,
        )
        logger.info("=" * 70)
        logger.info(f"API endpoint: http://{args.host}:{args.port}")
        logger.info(f"Ping: http://{args.host}:{args.port}/ping")
        logger.info(f"Health check: http://{args.host}:{args.port}/health")
        logger.info("=" * 70)
        uvicorn.run(server.app, host=args.host, port=args.port, log_level="info")
        logger.info("=" * 70)
        logger.info("Web server shutdown complete")
        logger.info("=" * 70)
    except KeyboardInterrupt:
        logger.info("Web server stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Failed to start web server", error=str(e), error_type=type(e).__name__)
        sys.exit(1)
