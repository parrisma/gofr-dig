"""GOFR-DIG Web Server entry point - Minimal stub implementation."""

import uvicorn
import argparse
import os
import sys

from app.web_server.web_server import GofrDigWebServer
from gofr_common.auth import (
    AuthService,
    GroupRegistry,
    JwtSecretProvider,
    create_stores_from_env,
    create_vault_client_from_env,
)
from app.logger import Logger, session_logger
import app.startup.validation

logger: Logger = session_logger

if __name__ == "__main__":
    seq_url_set = bool(os.environ.get("GOFR_DIG_SEQ_URL"))
    seq_api_key_set = bool(os.environ.get("GOFR_DIG_SEQ_API_KEY"))
    sink_status = "ok" if seq_url_set and seq_api_key_set else "degraded"
    sink_reason = (
        "vault_seq_credentials_available"
        if sink_status == "ok"
        else "missing_seq_url_or_api_key_falling_back_to_local_logging"
    )
    logger.info(
        "Logging sink initialized",
        event="logging_sink_initialized",
        operation="service_startup",
        stage="startup",
        dependency="seq",
        sink="seq",
        status=sink_status,
        reason=sink_reason,
        result=sink_status,
    )

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
        default=int(os.environ["GOFR_DIG_WEB_PORT"]),
        help="Port number to listen on (from GOFR_DIG_WEB_PORT env var)",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication (WARNING: insecure, for development only)",
    )
    args = parser.parse_args()

    auth_service = None
    if args.no_auth:
        logger.warning(
            "Authentication DISABLED - running in no-auth mode (INSECURE)",
            jwt_enabled=False,
        )
    else:
        try:
            vault_client = create_vault_client_from_env("GOFR_DIG", logger=logger)
            secret_provider = JwtSecretProvider(vault_client=vault_client, logger=logger)
            token_store, group_store = create_stores_from_env(
                "GOFR_DIG",
                vault_client=vault_client,
                logger=logger,
            )
            group_registry = GroupRegistry(store=group_store)
            auth_service = AuthService(
                token_store=token_store,
                group_registry=group_registry,
                secret_provider=secret_provider,
                env_prefix="GOFR_DIG",
                audience="gofr-api",
                logger=logger,
            )
            logger.info(
                "Authentication service initialized",
                jwt_enabled=True,
                backend=type(token_store).__name__,
            )
        except Exception as e:
            logger.error(
                "FATAL: Authentication initialization failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            sys.exit(1)

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
