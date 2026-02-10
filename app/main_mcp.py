import argparse
import os
import sys
import asyncio
from gofr_common.auth import AuthService, GroupRegistry, create_stores_from_env
from gofr_common.auth.config import resolve_auth_config
from app.logger import Logger, session_logger
import app.startup.validation

logger: Logger = session_logger

if __name__ == "__main__":
    # Validate data directory structure at startup
    try:
        app.startup.validation.validate_data_directory_structure(logger)
    except RuntimeError as e:
        logger.error("FATAL: Data directory validation failed", error=str(e))
        sys.exit(1)

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="GOFR-DIG MCP Server - Model Context Protocol Server"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host address to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ["GOFR_DIG_MCP_PORT"]),
        help="Port number to listen on (from GOFR_DIG_MCP_PORT env var)",
    )
    parser.add_argument(
        "--jwt-secret",
        type=str,
        default=None,
        help="JWT secret key (default: from GOFR_DIG_JWT_SECRET env var or auto-generated)",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication (WARNING: insecure, for development only)",
    )
    parser.add_argument(
        "--templates-dir",
        type=str,
        default=None,
        help="Path to templates directory (default: app/templates)",
    )
    parser.add_argument(
        "--styles-dir",
        type=str,
        default=None,
        help="Path to styles directory (default: app/styles)",
    )
    parser.add_argument(
        "--web-url",
        type=str,
        default=None,
        help="Web server base URL for proxy mode (default: from GOFR_DIG_WEB_URL env var or localhost)",
    )
    parser.add_argument(
        "--proxy-url-mode",
        type=str,
        choices=["guid", "url"],
        default="url",
        help="Proxy response mode: 'guid' returns only proxy_guid, 'url' returns both proxy_guid and full download_url (default: url)",
    )
    args = parser.parse_args()

    # Create logger for startup messages
    startup_logger: Logger = session_logger

    # Resolve authentication configuration
    jwt_secret, _require_auth = resolve_auth_config(
        env_prefix="GOFR_DIG",
        jwt_secret_arg=args.jwt_secret,
        require_auth=not args.no_auth,
        logger=startup_logger,
    )

    # Initialize auth service only if auth is required
    auth_service = None
    if jwt_secret:
        token_store, group_store = create_stores_from_env(prefix="GOFR_DIG")
        group_registry = GroupRegistry(store=group_store)
        auth_service = AuthService(
            token_store=token_store,
            group_registry=group_registry,
            secret_key=jwt_secret,
            env_prefix="GOFR_DIG",
        )
        startup_logger.info(
            "Authentication service initialized",
            jwt_enabled=True,
            backend=type(token_store).__name__,
        )
    else:
        startup_logger.warning(
            "Authentication DISABLED - running in no-auth mode (INSECURE)",
            jwt_enabled=False,
        )

    # Import and configure mcp_server with auth service
    import app.mcp_server.mcp_server as mcp_server_module

    mcp_server_module.auth_service = auth_service
    mcp_server_module.templates_dir_override = args.templates_dir
    mcp_server_module.styles_dir_override = args.styles_dir
    mcp_server_module.web_url_override = args.web_url
    mcp_server_module.proxy_url_mode = args.proxy_url_mode
    from app.mcp_server.mcp_server import main

    try:
        startup_logger.info("="*70)
        startup_logger.info("STARTING GOFR-DIG MCP SERVER")
        startup_logger.info("="*70)
        startup_logger.info(
            "Configuration",
            host=args.host,
            port=args.port,
            transport="HTTP Streamable",
            jwt_enabled=auth_service is not None,
            proxy_mode=args.proxy_url_mode.upper(),
            web_url=args.web_url or f"http://localhost:{os.environ['GOFR_DIG_WEB_PORT']}",
            templates_dir=args.templates_dir or "(default)",
            styles_dir=args.styles_dir or "(default)",
        )
        startup_logger.info("=" * 70)
        startup_logger.info(f"MCP endpoint: http://{args.host}:{args.port}/mcp")
        startup_logger.info("=" * 70)
        asyncio.run(main(host=args.host, port=args.port))
        startup_logger.info("=" * 70)
        startup_logger.info("MCP server shutdown complete")
        startup_logger.info("=" * 70)
    except KeyboardInterrupt:
        startup_logger.info("Shutdown complete")
        sys.exit(0)
    except Exception as e:
        startup_logger.error("Failed to start server", error=str(e), error_type=type(e).__name__)
        sys.exit(1)
