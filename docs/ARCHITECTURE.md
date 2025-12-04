# GOFR-DIG Architecture

This document describes the internal architecture of gofr-dig, including error handling, logging, authentication, and component interactions.

## Table of Contents

- [Overview](#overview)
- [Component Architecture](#component-architecture)
- [Error Handling](#error-handling)
- [Logging System](#logging-system)
- [Authentication](#authentication)
- [Scraping Pipeline](#scraping-pipeline)

---

## Overview

GOFR-DIG is structured as a modular MCP server with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Client                           │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                  Authentication Layer                   │
│            (JWT Token Verification)                     │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    MCP Server                           │
│         (Tool Registration & Dispatch)                  │
└─────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │  Scraper │    │ Structure│    │  Config  │
    │  Module  │    │ Analyzer │    │  Module  │
    └──────────┘    └──────────┘    └──────────┘
           │               │
           ▼               ▼
┌─────────────────────────────────────────────────────────┐
│                   Error Mapper                          │
│      (Exception → MCP Response Transformation)          │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    Session Logger                       │
│          (Request Tracking & Debugging)                 │
└─────────────────────────────────────────────────────────┘
```

---

## Component Architecture

### Entry Points

| Module | Purpose | Port |
|--------|---------|------|
| `main_mcp.py` | Pure MCP server (stdio or SSE) | 8030 |
| `main_mcpo.py` | MCP with OpenAPI wrapper | 8031 |
| `main_web.py` | Web server (REST API) | 8032 |

### Core Modules

#### `app/mcp_server/mcp_server.py`
The main MCP server implementation using the `mcp` library.

**Responsibilities:**
- Tool registration with schemas
- Request dispatch to handlers
- Response formatting
- Error boundary handling

**Key Classes:**
- `MCPServer` - Main server class with tool decorators

#### `app/scraping/`
Web scraping components organized by responsibility:

| File | Purpose |
|------|---------|
| `fetcher.py` | HTTP requests with session management |
| `extractor.py` | Content extraction from HTML |
| `structure.py` | Page structure analysis |
| `robots.py` | robots.txt parsing and compliance |
| `anti_detection.py` | Header profiles and evasion |

#### `app/auth/`
Authentication components:

| File | Purpose |
|------|---------|
| `service.py` | Token generation and validation |
| `middleware.py` | Request authentication |

#### `app/errors/`
Error handling infrastructure:

| File | Purpose |
|------|---------|
| `mapper.py` | Exception-to-response transformation |

#### `app/exceptions/`
Custom exception hierarchy:

| File | Purpose |
|------|---------|
| `base.py` | Base exception classes |

---

## Error Handling

### Exception Hierarchy

```python
GofrDigError                    # Base for all gofr-dig errors
├── ValidationError             # Input validation failures
│   └── INVALID_URL
│   └── INVALID_PROFILE
│   └── INVALID_RATE_LIMIT
├── ResourceNotFoundError       # Resource access failures
│   └── FETCH_ERROR
│   └── EXTRACTION_ERROR
├── SecurityError               # Security-related failures
│   └── ROBOTS_BLOCKED
│   └── AUTH_ERROR
└── ConfigurationError          # Configuration problems
    └── CONFIG_ERROR
```

### Error Mapper

The error mapper (`app/errors/mapper.py`) transforms exceptions into standardized MCP responses.

**Input:** Any exception
**Output:** Standardized error dict

```python
from app.errors.mapper import error_to_mcp_response

try:
    result = await scrape(url)
except Exception as e:
    return error_to_mcp_response(e)
```

### Error Response Format

```python
{
    "success": False,
    "error_code": str,          # Machine-readable code
    "error": str,               # Human-readable message
    "recovery_strategy": str,   # Actionable fix suggestion
    "details": dict             # Context-specific data
}
```

### Recovery Strategies

Each error code maps to a recovery strategy:

```python
RECOVERY_STRATEGIES = {
    "INVALID_URL": "Verify the URL includes a scheme (http:// or https://) and is properly formatted.",
    "FETCH_ERROR": "Check network connectivity and verify the URL is accessible. The site may be down or blocking requests.",
    "ROBOTS_BLOCKED": "The site's robots.txt disallows this request. Use set_antidetection with respect_robots_txt=false to override.",
    "EXTRACTION_ERROR": "Failed to extract content. Try a different CSS selector or check if the page structure has changed.",
    "INVALID_PROFILE": "Use one of the valid anti-detection profiles: 'stealth', 'balanced', 'none', or 'custom'.",
    "INVALID_RATE_LIMIT": "Rate limit must be between 0.1 and 60.0 seconds.",
    "AUTH_ERROR": "Authentication failed. Check your JWT token is valid and not expired.",
    "UNKNOWN_TOOL": "The requested tool does not exist. Available tools: ping, hello_world, set_antidetection, get_content, get_structure.",
}
```

### Error Code Mapping

The mapper converts specific exceptions to error codes:

```python
ERROR_CODE_MAP = {
    ValidationError: lambda e: getattr(e, 'error_code', 'VALIDATION_ERROR'),
    ResourceNotFoundError: lambda e: getattr(e, 'error_code', 'RESOURCE_NOT_FOUND'),
    SecurityError: lambda e: getattr(e, 'error_code', 'SECURITY_ERROR'),
    ValueError: lambda e: 'VALIDATION_ERROR',
    TimeoutError: lambda e: 'FETCH_ERROR',
    # ... more mappings
}
```

---

## Logging System

### Session Logger

The session logger (`app/logger/`) provides request-scoped logging with session tracking.

**Features:**
- Session ID tracking across related operations
- Log levels: DEBUG, INFO, WARNING, ERROR
- Console and file output
- Structured log format

### Logger Interface

```python
from app.logger import get_logger

logger = get_logger(__name__)

# With session context
logger.info("Processing request", extra={"session_id": session_id})

# Standard logging
logger.error("Operation failed", exc_info=True)
```

### Log Output Format

```
2024-01-15 10:23:45,123 - app.mcp_server - INFO - [session:abc123] Processing get_content request
2024-01-15 10:23:45,456 - app.scraping.fetcher - DEBUG - [session:abc123] Fetching URL: https://example.com
2024-01-15 10:23:46,789 - app.mcp_server - INFO - [session:abc123] Request completed successfully
```

### Logged Components

| Component | Events Logged |
|-----------|---------------|
| `auth/middleware.py` | Token verification, auth failures |
| `errors/mapper.py` | Exception mapping, recovery strategies |
| `mcp_server/mcp_server.py` | Tool invocations, request/response |
| `scraping/fetcher.py` | HTTP requests, retries |

---

## Authentication

### JWT Authentication

Authentication uses JWT (JSON Web Tokens) with configurable secret.

**Token Structure:**
```json
{
  "sub": "user_id",
  "exp": 1705312800,
  "iat": 1705226400,
  "scope": ["read", "write"]
}
```

### Middleware Flow

```
Request
   │
   ▼
┌─────────────────────┐
│ Check Authorization │
│      Header         │
└─────────────────────┘
   │
   ▼ (if present)
┌─────────────────────┐
│  Validate JWT Token │
│  - Signature check  │
│  - Expiry check     │
│  - Scope check      │
└─────────────────────┘
   │
   ▼ (if valid)
┌─────────────────────┐
│  Attach User Info   │
│   to Request        │
└─────────────────────┘
   │
   ▼
Handler
```

### Configuration

```bash
# Environment variables
GOFR_DIG_JWT_SECRET=your-secret-key
GOFR_DIG_TOKEN_STORE=/path/to/tokens.json

# Command line
python -m app.main_mcp --jwt-secret "your-secret-key"
```

### Token Management

Tokens can be managed via the `token_manager.sh` script:

```bash
# Generate new token
./scripts/token_manager.sh generate --user myuser

# List active tokens
./scripts/token_manager.sh list

# Revoke token
./scripts/token_manager.sh revoke --token-id abc123
```

---

## Scraping Pipeline

### Request Flow

```
get_content(url, depth=2)
         │
         ▼
┌─────────────────────┐
│   URL Validation    │
│   (scheme, format)  │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│   robots.txt Check  │
│   (if enabled)      │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│   Anti-Detection    │
│   Header Setup      │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│   Rate Limit Wait   │
│   (if configured)   │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│    HTTP Request     │
│   (with retries)    │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  Content Extraction │
│  - Text, links      │
│  - Headings, meta   │
└─────────────────────┘
         │
         ▼ (if depth > 1)
┌─────────────────────┐
│   Recursive Crawl   │
│   - Follow links    │
│   - Respect limits  │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  Response Assembly  │
│   - Main page       │
│   - Child pages     │
│   - Summary stats   │
└─────────────────────┘
```

### Anti-Detection Profiles

| Profile | User-Agent | Headers | Rate Limit |
|---------|------------|---------|------------|
| `stealth` | Chrome-like, rotating | Full browser set (Accept, Accept-Language, Accept-Encoding, Connection, Upgrade-Insecure-Requests) | 1.0s default |
| `balanced` | Modern Chrome | Standard set | 1.0s default |
| `none` | Python/httpx | Minimal | 0.5s default |
| `custom` | User-defined | User-defined | User-defined |

### Depth Crawling

When `depth > 1`, the crawler:

1. Fetches the root URL
2. Extracts internal links (same domain)
3. Filters already-visited URLs
4. Respects `max_pages_per_level` limit
5. Recursively fetches child pages
6. Aggregates results with depth metadata

**Constraints:**
- Maximum depth: 3
- Maximum pages per level: 100 (configurable)
- Only follows same-domain links
- Respects robots.txt for each URL

---

## Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `GOFR_DIG_DATA_DIR` | Data storage directory | `./data` |
| `GOFR_DIG_JWT_SECRET` | JWT signing secret | None (auth disabled) |
| `GOFR_DIG_TOKEN_STORE` | Token storage file | `{data_dir}/auth/tokens.json` |
| `GOFR_DIG_LOG_LEVEL` | Logging verbosity | `INFO` |
| `GOFR_DIG_LOG_FILE` | Log file path | `./logs/gofr-dig.log` |

### Runtime Configuration

Anti-detection settings are configured per-session via `set_antidetection`:

```python
# Session state stored in memory
session_config = {
    "profile": "balanced",
    "respect_robots_txt": True,
    "rate_limit_delay": 1.0,
    "custom_headers": {}
}
```

---

## Testing

### Test Structure

```
test/
├── conftest.py              # Shared fixtures
├── auth/
│   └── test_middleware.py   # Auth tests
├── errors/
│   └── test_error_mapper.py # Error mapping tests
├── exceptions/
│   └── test_exceptions.py   # Exception hierarchy tests
├── logger/
│   └── test_logging.py      # Logging tests
├── mcp/
│   ├── test_get_content.py  # Content extraction tests
│   ├── test_get_structure.py# Structure analysis tests
│   ├── test_hello_world.py  # Hello world tests
│   ├── test_depth_crawling.py # Recursive crawl tests
│   └── test_tool_schemas.py # Schema validation tests
└── scraping/
    ├── test_anti_detection.py
    ├── test_extractor.py
    ├── test_fetcher.py
    └── test_robots.py
```

### Running Tests

```bash
# All tests
./scripts/run_tests.sh

# Specific module
uv run pytest test/mcp/ -v

# With coverage
uv run pytest --cov=app --cov-report=html

# Single test
uv run pytest test/mcp/test_get_content.py::test_fetch_single_page -v
```

### Test Fixtures

Key fixtures in `conftest.py`:

- `mcp_server` - Configured MCP server instance
- `mock_fetcher` - Mocked HTTP client
- `test_html` - Sample HTML content
- `session_config` - Test session configuration
