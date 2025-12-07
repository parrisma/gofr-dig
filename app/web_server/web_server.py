"""GOFR-DIG Web Server - Minimal stub implementation for testing."""

from typing import Optional, Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from gofr_common.web import (
    create_cors_middleware,
    create_ping_response,
    create_health_response,
)
from app.auth import AuthService


class GofrDigWebServer:
    """Minimal web server for GOFR-DIG - provides basic endpoints."""

    SERVICE_NAME = "gofr-dig-web"

    def __init__(
        self,
        auth_service: Optional[AuthService] = None,
        host: str = "0.0.0.0",
        port: int = 8032,
    ):
        self.auth_service = auth_service
        self.host = host
        self.port = port
        self.app = self._create_app()

    def _create_app(self) -> Any:
        """Create the Starlette application."""
        routes = [
            Route("/", endpoint=self.root, methods=["GET"]),
            Route("/ping", endpoint=self.ping, methods=["GET"]),
            Route("/health", endpoint=self.health, methods=["GET"]),
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

    def get_app(self) -> Any:
        """Return the ASGI application."""
        return self.app
