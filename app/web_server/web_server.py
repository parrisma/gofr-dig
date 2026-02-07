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
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=404)
        except Exception as e:
            return JSONResponse({"detail": str(e)}, status_code=500)

    async def get_session_chunk(self, request: Request) -> Response:
        """Get session chunk content."""
        session_id = request.path_params["session_id"]
        chunk_index = request.path_params["chunk_index"]
        try:
            content = self.session_manager.get_chunk(session_id, chunk_index)
            # Return as plain text or JSON depending on content?
            # The tool returns JSON text, but here we might want raw content.
            # For now, return as plain text response if it's a string.
            from starlette.responses import PlainTextResponse
            return PlainTextResponse(content)
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=404)
        except Exception as e:
            return JSONResponse({"detail": str(e)}, status_code=500)

    def get_app(self) -> Any:
        """Return the ASGI application."""
        return self.app
