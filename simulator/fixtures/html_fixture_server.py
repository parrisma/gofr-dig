from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.logger import Logger, session_logger


@dataclass
class FixtureServerConfig:
    fixtures_dir: Path
    bind_host: str
    external_host: str
    port: int = 0


class HTMLFixtureServer:
    """Lightweight HTTP server for serving HTML test fixtures.

    This intentionally mirrors the behavior of the test fixture server in
    `test/conftest.py`, but is usable from the standalone simulator.

    Addressing:
    - bind_host: where the server binds (0.0.0.0 for Docker mode)
    - external_host: hostname placed into URLs returned by get_url/base_url
      (e.g. gofr-dig-dev on the shared docker network)

    Env defaults align with scripts/run_tests.sh:
      GOFR_DIG_FIXTURE_HOST=0.0.0.0
      GOFR_DIG_FIXTURE_EXTERNAL_HOST=gofr-dig-dev
    """

    def __init__(
        self,
        *,
        fixtures_dir: str | Path,
        port: int = 0,
        logger: Logger | None = None,
    ) -> None:
        self._logger = logger or session_logger
        self._fixtures_dir = Path(fixtures_dir)
        self.port = port

        self._bind_host = os.environ.get("GOFR_DIG_FIXTURE_HOST", "0.0.0.0")
        self._external_host = os.environ.get("GOFR_DIG_FIXTURE_EXTERNAL_HOST", "127.0.0.1")

        self._server = None
        self._thread = None

    def start(self) -> None:
        import http.server
        import threading

        fixtures_dir = self._fixtures_dir

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, directory=None, **kwargs):  # noqa: ARG002
                super().__init__(*args, directory=str(fixtures_dir), **kwargs)  # type: ignore[arg-type]

            def log_message(self, format, *args):  # noqa: A002, ARG002
                # Keep output deterministic and avoid noisy logs.
                pass

        class ReusableHTTPServer(http.server.HTTPServer):
            allow_reuse_address = True

        self._server = ReusableHTTPServer((self._bind_host, self.port), Handler)
        self.port = int(self._server.server_port)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        self._logger.info(
            "sim.fixture_server_started",
            event="sim.fixture_server_started",
            bind_host=self._bind_host,
            external_host=self._external_host,
            port=self.port,
            fixtures_dir=str(self._fixtures_dir),
        )

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        self._logger.info(
            "sim.fixture_server_stopped",
            event="sim.fixture_server_stopped",
            port=self.port,
        )

    def get_url(self, path: str = "") -> str:
        path = path.lstrip("/")
        return f"http://{self._external_host}:{self.port}/{path}"

    @property
    def base_url(self) -> str:
        return f"http://{self._external_host}:{self.port}"

    def __enter__(self) -> "HTMLFixtureServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
        return None
