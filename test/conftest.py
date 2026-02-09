"""Pytest configuration and fixtures

Provides shared fixtures for all tests, including temporary data directories,
auth service setup, and test server token management.
"""

import os
import sys
from pathlib import Path

import pytest

# Add project root to sys.path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from uuid import uuid4

from gofr_common.auth import AuthService, GroupRegistry
from gofr_common.auth.backends import VaultClient, VaultConfig, VaultGroupStore, VaultTokenStore
from app.config import Config


# ============================================================================
# AUTH AND TOKEN CONFIGURATION
# ============================================================================

# Shared JWT secret for all test servers and token generation
# Must match the secret used when launching test MCP/web servers
TEST_JWT_SECRET = "test-secret-key-for-secure-testing-do-not-use-in-production"

TEST_GROUP = "test_group"


def _create_test_auth_service(vault_client: VaultClient, path_prefix: str) -> AuthService:
    """Create an AuthService backed by Vault for testing.

    Uses a unique path prefix per test instance to isolate data.
    Automatically bootstraps reserved groups (public, admin) and creates
    the test_group used across the test suite.
    """
    token_store = VaultTokenStore(vault_client, path_prefix=path_prefix)
    group_store = VaultGroupStore(vault_client, path_prefix=path_prefix)
    group_registry = GroupRegistry(store=group_store)  # auto-bootstraps public, admin
    group_registry.create_group(TEST_GROUP, "Test group for test suite")

    return AuthService(
        token_store=token_store,
        group_registry=group_registry,
        secret_key=TEST_JWT_SECRET,
        env_prefix="GOFR_DIG",
    )


def _build_vault_client() -> VaultClient:
    """Create a VaultClient for tests using GOFR_DIG_VAULT_* env vars."""
    vault_url = os.environ.get("GOFR_DIG_VAULT_URL")
    vault_token = os.environ.get("GOFR_DIG_VAULT_TOKEN")

    if not vault_url or not vault_token:
        raise RuntimeError(
            "Vault test configuration missing. Set GOFR_DIG_VAULT_URL and "
            "GOFR_DIG_VAULT_TOKEN (run tests via ./scripts/run_tests.sh)."
        )

    config = VaultConfig(url=vault_url, token=vault_token)
    return VaultClient(config)


@pytest.fixture(scope="function", autouse=True)
def test_data_dir(tmp_path):
    """
    Automatically provide a temporary data directory for each test

    This fixture:
    - Creates a unique temporary directory for each test
    - Configures app.config to use this directory
    - Cleans up after the test completes
    """
    # Set up test mode with temporary directory
    test_dir = tmp_path / "gofr_dig_test_data"
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    (test_dir / "storage").mkdir(exist_ok=True)
    (test_dir / "auth").mkdir(exist_ok=True)

    # Configure for testing
    Config.set_test_mode(test_dir)

    yield test_dir

    Config.clear_test_mode()


@pytest.fixture(scope="function")
def temp_storage_dir(tmp_path):
    """
    Provide a temporary storage directory for specific tests that need it

    Returns:
        Path object pointing to temporary storage directory
    """
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


@pytest.fixture(scope="function")
def temp_auth_dir(tmp_path):
    """
    Provide a temporary auth directory for specific tests that need it

    Returns:
        Path object pointing to temporary auth directory
    """
    auth_dir = tmp_path / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    return auth_dir


@pytest.fixture(scope="session")
def test_auth_service():
    """
    Create an AuthService instance for testing with Vault stores.

    Uses VaultTokenStore and VaultGroupStore for isolation.
    Automatically creates reserved groups (public, admin) and TEST_GROUP.

    Returns:
        AuthService: Configured auth service with Vault stores
    """
    vault_client = _build_vault_client()
    path_prefix = f"gofr/tests/{uuid4()}"
    return _create_test_auth_service(vault_client, path_prefix)


@pytest.fixture(scope="function")
def test_jwt_token(test_auth_service):
    """
    Provide a valid JWT token for tests that require authentication.

    Token is created at test start and revoked at test end.

    Usage in tests:
        @pytest.mark.asyncio
        async def test_something(test_jwt_token):
            headers = {"Authorization": f"Bearer {test_jwt_token}"}
            # Use token in HTTP requests

    Returns:
        str: A valid JWT token for testing with 1 hour expiry
    """
    # Create token with 1 hour expiry
    token = test_auth_service.create_token(groups=[TEST_GROUP], expires_in_seconds=3600)

    yield token

    # Cleanup: revoke token after test
    try:
        test_auth_service.revoke_token(token)
    except Exception:
        pass  # Token may already be revoked or expired


# ============================================================================
# PHASE 4: CONSOLIDATED AUTH FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
def auth_service():
    """
    Create an isolated AuthService with Vault stores for each test.

    This is the standard fixture name used across most test files.
    Each test gets a fresh AuthService with no shared state.

    Returns:
        AuthService: Configured with TEST_JWT_SECRET and Vault stores
    """
    vault_client = _build_vault_client()
    path_prefix = f"gofr/tests/{uuid4()}"
    return _create_test_auth_service(vault_client, path_prefix)


@pytest.fixture(scope="function")
def mcp_headers(auth_service):
    """
    Provide pre-configured authentication headers for MCP server tests.

    Creates a token for 'test_group' with 1 hour expiry.

    Usage:
        async def test_mcp_endpoint(mcp_headers):
            async with MCPClient(MCP_URL) as client:
                result = await client.call_tool("tool_name", {...})
                # Headers automatically included

    Returns:
        Dict[str, str]: {"Authorization": "Bearer <token>"}
    """
    token = auth_service.create_token(groups=["test_group"], expires_in_seconds=3600)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session", autouse=True)
def configure_test_auth_environment():
    """
    Configure environment variables for test server authentication.

    This ensures test MCP/web servers use the same JWT secret and Vault backend
    as the test fixtures. Auto-runs before all tests.
    """
    os.environ["GOFR_DIG_JWT_SECRET"] = TEST_JWT_SECRET
    os.environ["GOFR_DIG_AUTH_BACKEND"] = "vault"

    # Default to local test vault if not already set
    os.environ.setdefault("GOFR_DIG_VAULT_URL", "http://localhost:8301")
    os.environ.setdefault("GOFR_DIG_VAULT_TOKEN", "gofr-dev-root-token")

    yield

    # Cleanup
    os.environ.pop("GOFR_DIG_JWT_SECRET", None)
    os.environ.pop("GOFR_DIG_AUTH_BACKEND", None)
    os.environ.pop("GOFR_DIG_VAULT_URL", None)
    os.environ.pop("GOFR_DIG_VAULT_TOKEN", None)


# ============================================================================
# TEST SERVER MANAGEMENT
# ============================================================================

# Import ServerManager for managing test servers
try:
    # Try to import ServerManager - may fail if not in the test directory
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from test_server_manager import ServerManager  # type: ignore[import-not-found]
except (ImportError, ModuleNotFoundError):
    ServerManager = None  # type: ignore[misc, assignment]


@pytest.fixture(scope="session")
def test_server_manager():
    """
    Create a ServerManager for controlling test servers in auth mode.

    This manages the lifecycle of MCP and web servers for integration testing.
    Servers started with this manager will use the shared JWT secret and
    token store configured in configure_test_auth_environment.

    Usage:
        def test_with_server(test_server_manager, test_data_dir):
            # Start MCP server with auth enabled
            success = test_server_manager.start_mcp_server(
                templates_dir=str(test_data_dir / "docs/templates"),
                styles_dir=str(test_data_dir / "docs/styles"),
                storage_dir=str(test_data_dir / "storage"),
            )
            if not success:
                pytest.skip("MCP server failed to start")

            # Server is ready at: test_server_manager.get_mcp_url()

            yield  # Test runs with server active

            # Server automatically stops here when fixture context ends

    Returns:
        ServerManager: Server manager instance, or None if import failed
    """
    if ServerManager is None:
        return None

    manager = ServerManager(
        jwt_secret=TEST_JWT_SECRET,
        mcp_port=8013,
        web_port=8000,
    )

    yield manager

    # Cleanup: stop all servers
    manager.stop_all()


# ============================================================================
# MOCK IMAGE SERVER FOR TESTING
# ============================================================================


@pytest.fixture(scope="function")
def image_server():
    """
    Provide a lightweight HTTP server for serving test images.

    The server serves files from test/mock/data directory on port 8765.
    Use image_server.get_url(filename) to get the full URL for a test image.

    Usage:
        def test_image_download(image_server):
            url = image_server.get_url("graph.png")
            # url is "http://localhost:8765/graph.png"
            # Make requests to this URL

    Returns:
        ImageServer: Server instance with start(), stop(), and get_url() methods
    """
    import sys
    from pathlib import Path

    # Add test directory to path for imports
    test_dir = Path(__file__).parent
    if str(test_dir) not in sys.path:
        sys.path.insert(0, str(test_dir))

    from mock.image_server import ImageServer  # type: ignore[import-not-found]

    server = ImageServer(port=8765)
    server.start()

    yield server

    server.stop()


# ============================================================================
# HTML FIXTURE SERVER FOR SCRAPING TESTS
# ============================================================================


class HTMLFixtureServer:
    """Simple HTTP server for serving HTML test fixtures.

    Bind address and external hostname are controlled by env vars so that
    Docker-based integration tests (where test containers need to reach this
    server over the shared network) work alongside local runs.

    Env vars (set by run_tests.sh --docker / --no-docker):
      GOFR_DIG_FIXTURE_HOST          — bind address (default 0.0.0.0)
      GOFR_DIG_FIXTURE_EXTERNAL_HOST — hostname used in URLs returned by
                                        get_url() / base_url (default 127.0.0.1)
    """

    def __init__(self, port: int = 8766):
        self.port = port
        self._bind_host = os.environ.get("GOFR_DIG_FIXTURE_HOST", "0.0.0.0")
        self._external_host = os.environ.get("GOFR_DIG_FIXTURE_EXTERNAL_HOST", "127.0.0.1")
        self._server = None
        self._thread = None
        self._fixtures_dir = Path(__file__).parent / "fixtures" / "html"

    def start(self):
        """Start the HTTP server in a background thread."""
        import http.server
        import threading

        # Capture fixtures_dir in closure for the nested Handler class
        fixtures_dir = self._fixtures_dir

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, directory=None, **kwargs):  # noqa: ARG002
                super().__init__(*args, directory=str(fixtures_dir), **kwargs)  # type: ignore[arg-type]

            def log_message(self, format, *args):  # noqa: A002, ARG002
                pass  # Suppress logging

        self._server = http.server.HTTPServer((self._bind_host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def get_url(self, path: str = "") -> str:
        """Get the full URL for a path on this server."""
        path = path.lstrip("/")
        return f"http://{self._external_host}:{self.port}/{path}"

    @property
    def base_url(self) -> str:
        """Get the base URL of the server."""
        return f"http://{self._external_host}:{self.port}"


@pytest.fixture(scope="function")
def html_fixture_server():
    """
    Provide a lightweight HTTP server for serving HTML test fixtures.

    The server serves files from test/fixtures/html directory on port 8766.
    Use html_fixture_server.get_url(path) to get the full URL for a test page.

    Available pages:
    - index.html - Home page with navigation
    - products.html - Product listing
    - product-detail.html - Product detail page
    - about.html - About page
    - contact.html - Contact form
    - blog/index.html - Blog listing
    - blog/post-1.html - Blog post with multilingual content
    - chinese.html - Full Chinese content
    - japanese.html - Full Japanese content
    - external-links.html - Page with external links
    - script-heavy.html - JavaScript-heavy dashboard
    - robots.txt - Robots exclusion file

    Usage:
        def test_scrape_page(html_fixture_server):
            url = html_fixture_server.get_url("products.html")
            # url is "http://127.0.0.1:8766/products.html"
            # Make requests to this URL

    Returns:
        HTMLFixtureServer: Server instance with start(), stop(), get_url(), and base_url
    """
    server = HTMLFixtureServer(port=8766)
    server.start()

    yield server

    server.stop()


@pytest.fixture(scope="session")
def html_fixture_server_session():
    """
    Session-scoped HTML fixture server for tests that need persistent server.

    Same as html_fixture_server but lives for the entire test session.
    Uses port 8767 to avoid conflicts with function-scoped fixture.

    Returns:
        HTMLFixtureServer: Server instance
    """
    server = HTMLFixtureServer(port=8767)
    server.start()

    yield server

    server.stop()
