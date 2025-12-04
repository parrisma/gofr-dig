"""GOFR-DIG Web Server - Minimal stub implementation for testing."""

import json
from typing import Optional, Any

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.auth import AuthService
from app.logger import session_logger as logger


class GofrDigWebServer:
    """Minimal web server for GOFR-DIG - provides basic endpoints."""

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

        # Add CORS middleware
        app = CORSMiddleware(
            app,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

        return app

    async def root(self, request: Request) -> JSONResponse:
        """Root endpoint."""
        return JSONResponse({
            "service": "gofr-dig-web",
            "status": "ok",
            "message": "GOFR-DIG Web Server - Stub Implementation",
        })

    async def ping(self, request: Request) -> JSONResponse:
        """Health check ping endpoint."""
        return JSONResponse({"status": "ok", "service": "gofr-dig-web"})

    async def health(self, request: Request) -> JSONResponse:
        """Health check endpoint."""
        return JSONResponse({
            "status": "healthy",
            "service": "gofr-dig-web",
            "auth_enabled": self.auth_service is not None,
        })

    def get_app(self) -> Any:
        """Return the ASGI application."""
        return self.app
