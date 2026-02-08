"""GOFR-DIG Web Server - Minimal stub implementation for testing."""

from typing import Optional, Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from gofr_common.web import (
    create_cors_middleware,
    create_ping_response,
    create_health_response,
)
from gofr_common.auth import AuthService
from app.session.manager import SessionManager
from app.config import Config
from app.exceptions import GofrDigError, SessionNotFoundError, SessionValidationError
from app.errors.mapper import error_to_web_response
from app.logger import session_logger as logger


class GofrDigWebServer:
    """Minimal web server for GOFR-DIG - provides basic endpoints."""

    SERVICE_NAME = "gofr-dig-web"

    def __init__(
        self,
        auth_service: Optional[AuthService] = None,
        host: str = "0.0.0.0",
        port: int = 8072,
    ):
        self.auth_service = auth_service
        self.host = host
        self.port = port
        
        # Initialize session manager
        storage_dir = Config.get_storage_dir() / "sessions"
        self.session_manager = SessionManager(storage_dir)
        
        self.app = self._create_app()

    def _create_app(self) -> Any:
        """Create the Starlette application."""
        routes = [
            Route("/", endpoint=self.root, methods=["GET"]),
            Route("/ping", endpoint=self.ping, methods=["GET"]),
            Route("/health", endpoint=self.health, methods=["GET"]),
            Route("/sessions/{session_id}/info", endpoint=self.get_session_info, methods=["GET"]),
            Route("/sessions/{session_id}/chunks/{chunk_index:int}", endpoint=self.get_session_chunk, methods=["GET"]),
            Route("/sessions/{session_id}/urls", endpoint=self.get_session_urls, methods=["GET"]),
        ]

        app = Starlette(debug=False, routes=routes)

        # Add CORS middleware using gofr_common
        app = create_cors_middleware(app)

        return app

    async def root(self, request: Request) -> JSONResponse:
        """Root endpoint."""
        return JSONResponse({
            "service": self.SERVICE_NAME,
            "status": "ok",
            "message": "GOFR-DIG Web Server - Stub Implementation",
        })

    async def ping(self, request: Request) -> JSONResponse:
        """Health check ping endpoint."""
        return JSONResponse(create_ping_response(self.SERVICE_NAME))

    async def health(self, request: Request) -> JSONResponse:
        """Health check endpoint."""
        return JSONResponse(create_health_response(
            service=self.SERVICE_NAME,
            auth_enabled=self.auth_service is not None,
        ))

    async def get_session_info(self, request: Request) -> Response:
        """Get session metadata."""
        session_id = request.path_params["session_id"]
        try:
            info = self.session_manager.get_session_info(session_id)
            return JSONResponse(info)
        except SessionNotFoundError as e:
            logger.warning("Session not found", session_id=session_id)
            return JSONResponse(error_to_web_response(e), status_code=404)
        except GofrDigError as e:
            logger.error("Session error", session_id=session_id, error=str(e))
            return JSONResponse(error_to_web_response(e), status_code=400)
        except Exception as e:
            logger.error(
                "Unexpected error in get_session_info",
                session_id=session_id,
                error=str(e),
                cause=type(e).__name__,
            )
            return JSONResponse(
                {"error": {"code": "INTERNAL_ERROR", "message": str(e)}},
                status_code=500,
            )

    async def get_session_chunk(self, request: Request) -> Response:
        """Get session chunk content."""
        session_id = request.path_params["session_id"]
        chunk_index = request.path_params["chunk_index"]
        try:
            content = self.session_manager.get_chunk(session_id, chunk_index)
            from starlette.responses import PlainTextResponse
            return PlainTextResponse(content)
        except SessionNotFoundError as e:
            logger.warning("Session not found", session_id=session_id)
            return JSONResponse(error_to_web_response(e), status_code=404)
        except SessionValidationError as e:
            logger.warning(
                "Invalid chunk index",
                session_id=session_id,
                chunk_index=chunk_index,
            )
            return JSONResponse(error_to_web_response(e), status_code=400)
        except GofrDigError as e:
            logger.error(
                "Session error",
                session_id=session_id,
                chunk_index=chunk_index,
                error=str(e),
            )
            return JSONResponse(error_to_web_response(e), status_code=400)
        except Exception as e:
            logger.error(
                "Unexpected error in get_session_chunk",
                session_id=session_id,
                chunk_index=chunk_index,
                error=str(e),
                cause=type(e).__name__,
            )
            return JSONResponse(
                {"error": {"code": "INTERNAL_ERROR", "message": str(e)}},
                status_code=500,
            )

    async def get_session_urls(self, request: Request) -> Response:
        """Get a list of chunk URLs for a session.

        Returns ready-to-GET REST URLs that automation services can iterate.
        Auto-detects base URL from request Host header or GOFR_DIG_WEB_URL env var.
        """
        import os

        session_id = request.path_params["session_id"]

        # Resolve base URL: query param → env var → request Host header
        base_url = request.query_params.get("base_url")
        if not base_url:
            base_url = os.environ.get("GOFR_DIG_WEB_URL")
        if not base_url:
            scheme = request.headers.get("x-forwarded-proto", "http")
            host = request.headers.get("x-forwarded-host", request.headers.get("host", f"localhost:{self.port}"))
            base_url = f"{scheme}://{host}"
        base_url = base_url.rstrip("/")

        try:
            info = self.session_manager.get_session_info(session_id)
            total_chunks = info["total_chunks"]
            chunk_urls = [
                f"{base_url}/sessions/{session_id}/chunks/{i}"
                for i in range(total_chunks)
            ]
            return JSONResponse({
                "success": True,
                "session_id": session_id,
                "url": info.get("url", ""),
                "total_chunks": total_chunks,
                "chunk_urls": chunk_urls,
            })
        except SessionNotFoundError as e:
            logger.warning("Session not found", session_id=session_id)
            return JSONResponse(error_to_web_response(e), status_code=404)
        except GofrDigError as e:
            logger.error("Session error", session_id=session_id, error=str(e))
            return JSONResponse(error_to_web_response(e), status_code=400)
        except Exception as e:
            logger.error(
                "Unexpected error in get_session_urls",
                session_id=session_id,
                error=str(e),
                cause=type(e).__name__,
            )
            return JSONResponse(
                {"error": {"code": "INTERNAL_ERROR", "message": str(e)}},
                status_code=500,
            )

    def get_app(self) -> Any:
        """Return the ASGI application."""
        return self.app
