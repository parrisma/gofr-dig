"""MCPO wrapper implementation for GOFR-DIG MCP server

Provides both authenticated and non-authenticated MCPO proxy modes.
"""

import asyncio
import os
import subprocess
from typing import Optional

from app.logger import Logger, session_logger

logger: Logger = session_logger

# Port defaults from environment (set by gofr_ports.env; 0 = not configured)
_MCP_PORT = int(os.environ.get("GOFR_DIG_MCP_PORT", "0"))
_MCPO_PORT = int(os.environ.get("GOFR_DIG_MCPO_PORT", "0"))


class MCPOWrapper:
    """Wrapper for MCPO proxy server"""

    def __init__(
        self,
        mcp_host: str = "localhost",
        mcp_port: int = _MCP_PORT,
        mcpo_port: int = _MCPO_PORT,
        mcpo_host: str = "0.0.0.0",
        mcpo_api_key: Optional[str] = None,
        auth_token: Optional[str] = None,
        use_auth: bool = False,
    ):
        """
        Initialize MCPO wrapper

        Args:
            mcp_host: Host where MCP server is running
            mcp_port: Port where MCP server is listening
            mcpo_port: Port for MCPO proxy to listen on
            mcpo_host: Host for MCPO proxy to bind to (default: 0.0.0.0)
            mcpo_api_key: API key for Open WebUI -> MCPO authentication (None = no API key)
            auth_token: JWT token for MCPO -> MCP authentication (if use_auth=True)
            use_auth: Whether to use authenticated mode
        """
        self.mcp_host = mcp_host
        self.mcp_port = mcp_port
        self.mcpo_port = mcpo_port
        self.mcpo_host = mcpo_host
        self.mcpo_api_key = mcpo_api_key
        self.auth_token = auth_token
        self.use_auth = use_auth
        self.process: Optional[subprocess.Popen] = None

    def _build_mcpo_command(self) -> list[str]:
        """Build the MCPO command line"""
        mcp_url = f"http://{self.mcp_host}:{self.mcp_port}/mcp"

        # Base command
        cmd = [
            "uv",
            "tool",
            "run",
            "mcpo",
            "--host",
            self.mcpo_host,
            "--port",
            str(self.mcpo_port),
            "--server-type",
            "streamable-http",
        ]

        # Add API key if provided
        if self.mcpo_api_key:
            cmd.extend(["--api-key", self.mcpo_api_key])

        # Add auth header if in authenticated mode
        if self.use_auth:
            if not self.auth_token:
                raise ValueError("auth_token required when use_auth=True")
            cmd.extend(["--header", f'{{"Authorization": "Bearer {self.auth_token}"}}'])

        # Add MCP server URL
        cmd.extend(["--", mcp_url])

        return cmd

    def start(self) -> None:
        """Start the MCPO proxy server"""
        cmd = self._build_mcpo_command()

        mode = "authenticated" if self.use_auth else "public (no auth)"
        logger.info(
            f"Starting MCPO wrapper in {mode} mode",
            mcp_url=f"http://{self.mcp_host}:{self.mcp_port}/mcp",
            mcpo_bind=f"{self.mcpo_host}:{self.mcpo_port}",
            use_auth=self.use_auth,
            command=" ".join(cmd),
        )

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            logger.info(
                "MCPO proxy process started",
                pid=self.process.pid,
                mcpo_port=self.mcpo_port,
                mcp_url=f"http://{self.mcp_host}:{self.mcp_port}/mcp",
            )
        except Exception as e:
            logger.error("Failed to start MCPO proxy", error=str(e), error_type=type(e).__name__)
            raise

    def stop(self) -> None:
        """Stop the MCPO proxy server"""
        if self.process:
            logger.info("Stopping MCPO proxy", pid=self.process.pid)
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("MCPO proxy did not terminate gracefully, forcing shutdown")
                self.process.kill()
            self.process = None

    def is_running(self) -> bool:
        """Check if MCPO proxy is running"""
        if self.process is None:
            return False

        returncode = self.process.poll()
        if returncode is not None:
            # Process exited - capture output for debugging
            stdout, stderr = "", ""
            try:
                stdout, stderr = self.process.communicate(timeout=1)
            except Exception:
                pass

            logger.error(
                "MCPO proxy process exited unexpectedly",
                pid=self.process.pid,
                returncode=returncode,
                mcpo_port=self.mcpo_port,
                mcp_url=f"http://{self.mcp_host}:{self.mcp_port}/mcp",
                stdout=stdout[:500] if stdout else "(empty)",
                stderr=stderr[:500] if stderr else "(empty)",
            )
            return False
        return True

    async def run_async(self) -> None:
        """Run MCPO proxy and wait for it to complete"""
        self.start()
        if self.process:
            # Wait for process to complete
            await asyncio.get_event_loop().run_in_executor(None, self.process.wait)


def start_mcpo_wrapper(
    mcp_host: str = "localhost",
    mcp_port: int = _MCP_PORT,
    mcpo_port: int = _MCPO_PORT,
    mcpo_host: str = "0.0.0.0",
    mcpo_api_key: Optional[str] = None,
    auth_token: Optional[str] = None,
    use_auth: bool = False,
) -> MCPOWrapper:
    """
    Start MCPO wrapper for GOFR-DIG MCP server

    Args:
        mcp_host: Host where MCP server is running (default: localhost)
        mcp_port: Port where MCP server is listening (from GOFR_DIG_MCP_PORT env var)
        mcpo_port: Port for MCPO proxy to listen on (from GOFR_DIG_MCPO_PORT env var)
        mcpo_host: Host for MCPO proxy to bind to (default: 0.0.0.0)
        mcpo_api_key: API key for Open WebUI -> MCPO (default: from env or None for no auth)
        auth_token: JWT token for MCPO -> MCP (default: from env or None)
        use_auth: Whether to use authenticated mode (default: False)

    Returns:
        MCPOWrapper instance

    Environment Variables:
        GOFR_DIG_MCPO_API_KEY: API key for MCPO authentication (if not set, no API key required)
        GOFR_DIG_JWT_TOKEN: JWT token for MCP server authentication
        GOFR_DIG_MCPO_MODE: 'auth' or 'public' (overrides use_auth parameter)
    """
    # Resolve API key from environment if not explicitly provided
    if mcpo_api_key is None:
        mcpo_api_key = os.environ.get("GOFR_DIG_MCPO_API_KEY")

    # Resolve auth token
    if auth_token is None:
        auth_token = os.environ.get("GOFR_DIG_JWT_TOKEN")

    # Resolve auth mode from environment
    mode = os.environ.get("GOFR_DIG_MCPO_MODE", "").lower()
    if mode == "auth":
        use_auth = True
    elif mode == "public":
        use_auth = False

    wrapper = MCPOWrapper(
        mcp_host=mcp_host,
        mcp_port=mcp_port,
        mcpo_port=mcpo_port,
        mcpo_host=mcpo_host,
        mcpo_api_key=mcpo_api_key,
        auth_token=auth_token,
        use_auth=use_auth,
    )
    wrapper.start()
    return wrapper
