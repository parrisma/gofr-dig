"""GOFR-DIG Web Server - Minimal stub implementation for testing."""

import os
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

try:
    from gofr_common.auth.exceptions import AuthError
except ImportError:
    AuthError = None  # type: ignore[assignment,misc]

try:
    from gofr_common.storage.exceptions import PermissionDeniedError
except ImportError:
    PermissionDeniedError = None  # type: ignore[assignment,misc]


class GofrDigWebServer:
    """Minimal web server for GOFR-DIG - provides basic endpoints."""

    SERVICE_NAME = "gofr-dig-web"

    def __init__(
        self,
        auth_service: Optional[AuthService] = None,
        host: str = "0.0.0.0",
        port: int = int(os.environ.get("GOFR_DIG_WEB_PORT", "0")),
    ):
        self.auth_service = auth_service
        self.host = host
        self.port = port
        
        # Initialize session manager
        storage_dir = Config.get_storage_dir() / "sessions"
        self.session_manager = SessionManager(storage_dir)
        
        self.app = self._create_app()

    def _resolve_group(self, request: Request) -> str | None:
        """Resolve primary group from Authorization header.

        Returns group string or None for anonymous/no-auth.
        Raises AuthError (from gofr_common) if token is invalid.
        """
        if self.auth_service is None:
            return None

        auth_header = request.headers.get("authorization", "")
        if not auth_header:
            return None

        raw = auth_header.removeprefix("Bearer ").removeprefix("bearer ").strip()
        if not raw:
            return None

        token_info = self.auth_service.verify_token(raw)
        return token_info.groups[0] if token_info.groups else None

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

    @staticmethod
    def _request_id(request: Request) -> str | None:
        return request.headers.get("x-request-id")

    def _log_session_issue(
        self,
        level: str,
        message: str,
        request: Request,
        session_id: str,
        *,
        error_code: str,
        side_effect: str,
        remediation: str,
        cause_type: str,
        chunk_index: int | None = None,
    ) -> None:
        fields = {
            "event": "session_retrieval_failed",
            "operation": request.url.path,
            "stage": "respond",
            "dependency": "storage",
            "request_id": self._request_id(request),
            "session_id": session_id,
            "chunk_index": chunk_index,
            "root_cause_code": error_code,
            "error_code": error_code,
            "cause_type": cause_type,
            "side_effect": side_effect,
            "impact": side_effect,
            "remediation": remediation,
        }
        payload = {k: v for k, v in fields.items() if v is not None}
        if level == "warning":
            logger.warning(message, **payload)
        else:
            logger.error(message, **payload)

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
            group = self._resolve_group(request)
        except Exception as e:
            if AuthError is not None and isinstance(e, AuthError):
                return JSONResponse({"error": {"code": "AUTH_ERROR", "message": str(e)}}, status_code=401)
            raise
        try:
            info = self.session_manager.get_session_info(session_id, group=group)
            return JSONResponse(info)
        except Exception as e:
            if PermissionDeniedError is not None and isinstance(e, PermissionDeniedError):
                return JSONResponse({"error": {"code": "PERMISSION_DENIED", "message": str(e)}}, status_code=403)
            if isinstance(e, SessionNotFoundError):
                self._log_session_issue(
                    "warning",
                    "Session not found",
                    request,
                    session_id,
                    error_code="SESSION_NOT_FOUND",
                    side_effect="session_not_accessible",
                    remediation="verify_session_id_or_create_a_new_session",
                    cause_type=type(e).__name__,
                )
                return JSONResponse(error_to_web_response(e), status_code=404)
            if isinstance(e, GofrDigError):
                self._log_session_issue(
                    "error",
                    "Session error",
                    request,
                    session_id,
                    error_code=getattr(e, "error_code", "SESSION_ERROR"),
                    side_effect="session_info_not_returned",
                    remediation="review_error_code_and_retry_with_valid_session",
                    cause_type=type(e).__name__,
                )
                return JSONResponse(error_to_web_response(e), status_code=400)
            self._log_session_issue(
                "error",
                "Unexpected error in get_session_info",
                request,
                session_id,
                error_code="INTERNAL_ERROR",
                side_effect="session_info_not_returned",
                remediation="inspect_server_logs_and_retry_request",
                cause_type=type(e).__name__,
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
            group = self._resolve_group(request)
        except Exception as e:
            if AuthError is not None and isinstance(e, AuthError):
                return JSONResponse({"error": {"code": "AUTH_ERROR", "message": str(e)}}, status_code=401)
            raise
        try:
            content = self.session_manager.get_chunk(session_id, chunk_index, group=group)
            from starlette.responses import PlainTextResponse
            return PlainTextResponse(content)
        except Exception as e:
            if PermissionDeniedError is not None and isinstance(e, PermissionDeniedError):
                return JSONResponse({"error": {"code": "PERMISSION_DENIED", "message": str(e)}}, status_code=403)
            if isinstance(e, SessionNotFoundError):
                self._log_session_issue(
                    "warning",
                    "Session not found",
                    request,
                    session_id,
                    error_code="SESSION_NOT_FOUND",
                    side_effect="session_chunk_not_returned",
                    remediation="verify_session_id_or_create_a_new_session",
                    cause_type=type(e).__name__,
                    chunk_index=chunk_index,
                )
                return JSONResponse(error_to_web_response(e), status_code=404)
            if isinstance(e, SessionValidationError):
                self._log_session_issue(
                    "warning",
                    "Invalid chunk index",
                    request,
                    session_id,
                    error_code=getattr(e, "error_code", "SESSION_VALIDATION_ERROR"),
                    side_effect="session_chunk_not_returned",
                    remediation="provide_chunk_index_within_session_range",
                    cause_type=type(e).__name__,
                    chunk_index=chunk_index,
                )
                return JSONResponse(error_to_web_response(e), status_code=400)
            if isinstance(e, GofrDigError):
                self._log_session_issue(
                    "error",
                    "Session error",
                    request,
                    session_id,
                    error_code=getattr(e, "error_code", "SESSION_ERROR"),
                    side_effect="session_chunk_not_returned",
                    remediation="review_error_code_and_retry_with_valid_session",
                    cause_type=type(e).__name__,
                    chunk_index=chunk_index,
                )
                return JSONResponse(error_to_web_response(e), status_code=400)
            self._log_session_issue(
                "error",
                "Unexpected error in get_session_chunk",
                request,
                session_id,
                error_code="INTERNAL_ERROR",
                side_effect="session_chunk_not_returned",
                remediation="inspect_server_logs_and_retry_request",
                cause_type=type(e).__name__,
                chunk_index=chunk_index,
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

        try:
            group = self._resolve_group(request)
        except Exception as e:
            if AuthError is not None and isinstance(e, AuthError):
                return JSONResponse({"error": {"code": "AUTH_ERROR", "message": str(e)}}, status_code=401)
            raise

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
            info = self.session_manager.get_session_info(session_id, group=group)
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
        except Exception as e:
            if PermissionDeniedError is not None and isinstance(e, PermissionDeniedError):
                return JSONResponse({"error": {"code": "PERMISSION_DENIED", "message": str(e)}}, status_code=403)
            if isinstance(e, SessionNotFoundError):
                self._log_session_issue(
                    "warning",
                    "Session not found",
                    request,
                    session_id,
                    error_code="SESSION_NOT_FOUND",
                    side_effect="session_urls_not_returned",
                    remediation="verify_session_id_or_create_a_new_session",
                    cause_type=type(e).__name__,
                )
                return JSONResponse(error_to_web_response(e), status_code=404)
            if isinstance(e, GofrDigError):
                self._log_session_issue(
                    "error",
                    "Session error",
                    request,
                    session_id,
                    error_code=getattr(e, "error_code", "SESSION_ERROR"),
                    side_effect="session_urls_not_returned",
                    remediation="review_error_code_and_retry_with_valid_session",
                    cause_type=type(e).__name__,
                )
                return JSONResponse(error_to_web_response(e), status_code=400)
            self._log_session_issue(
                "error",
                "Unexpected error in get_session_urls",
                request,
                session_id,
                error_code="INTERNAL_ERROR",
                side_effect="session_urls_not_returned",
                remediation="inspect_server_logs_and_retry_request",
                cause_type=type(e).__name__,
            )
            return JSONResponse(
                {"error": {"code": "INTERNAL_ERROR", "message": str(e)}},
                status_code=500,
            )

    def get_app(self) -> Any:
        """Return the ASGI application."""
        return self.app
