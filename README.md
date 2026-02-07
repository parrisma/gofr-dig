# gofr-dig

**GOFR-DIG** is an MCP (Model Context Protocol) server for web scraping with anti-detection capabilities. It provides tools for extracting content and analyzing structure from web pages, with built-in support for robots.txt compliance, rate limiting, and browser-like request headers.

## Features

- 🔍 **Content Extraction** - Extract text, links, images, and metadata from web pages
- 🕸️ **Recursive Crawling** - Follow links up to 3 levels deep
- 🛡️ **Anti-Detection** - Configurable profiles to avoid bot detection
- 🤖 **robots.txt Compliance** - Respects site crawling rules by default
- ⏱️ **Rate Limiting** - Configurable delays between requests
- 📊 **Structure Analysis** - Analyze page layout, forms, and navigation

## Quick Start

```bash
# Install dependencies
uv pip install -e .

# Start MCP server
python -m app.main_mcp --port 8070

# Start with authentication
python -m app.main_mcp --port 8070 --jwt-secret "your-secret-key"
```

## MCP Tools

### `ping`
Health check - verifies server is running.

```json
// Returns
{"status": "ok", "service": "gofr-dig"}
```

### `hello_world`
Test tool that returns a greeting.

```json
// Input
{"name": "Claude"}
// Returns
{"message": "Hello, Claude!"}
```

### `set_antidetection`
Configure anti-detection settings before scraping.

```json
// Input
{
  "profile": "balanced",        // stealth | balanced | none | custom
  "respect_robots_txt": true,   // Honor robots.txt rules
  "rate_limit_delay": 1.0       // Seconds between requests
}
// Returns
{"success": true, "profile": "balanced", ...}
```

**Profiles:**
- `stealth` - Maximum protection with full browser headers
- `balanced` - Good protection for most sites (recommended)
- `none` - Minimal headers, fastest but easily detected
- `custom` - Define your own headers

### `get_content`
Fetch and extract text content from web pages.

```json
// Single page
{"url": "https://example.com/page"}

// Recursive crawl (depth 2, max 5 pages per level)
{
  "url": "https://docs.example.com",
  "depth": 2,
  "max_pages_per_level": 5
}

// With CSS selector
{
  "url": "https://example.com",
  "selector": "#main-content"
}
```

**Returns for single page (depth=1):**
```json
{
  "success": true,
  "url": "https://example.com/page",
  "title": "Page Title",
  "text": "Extracted text content...",
  "language": "en",
  "links": [...],
  "headings": [...],
  "meta": {...}
}
```

**Returns for multi-page crawl (depth>1):**
```json
{
  "success": true,
  "url": "https://example.com",
  "title": "Home",
  "text": "Root page text...",
  "pages": [
    {"depth": 1, "url": "...", "title": "...", "text": "..."},
    {"depth": 2, "url": "...", "title": "...", "text": "..."}
  ],
  "summary": {
    "total_pages": 6,
    "total_text_length": 45000,
    "pages_by_depth": {"1": 1, "2": 5}
  }
}
```

### `get_structure`
Analyze page structure without extracting all text.

```json
// Input
{"url": "https://example.com"}

// Returns
{
  "success": true,
  "url": "https://example.com",
  "title": "Example",
  "sections": [...],
  "navigation": [...],
  "internal_links": [...],
  "external_links": [...],
  "forms": [...],
  "outline": [...]
}
```

Use `get_structure` to understand page layout before using `get_content` with a specific selector.

## Error Handling

All tools return standardized error responses:

```json
{
  "success": false,
  "error_code": "ROBOTS_BLOCKED",
  "error": "Access denied: Disallowed by robots.txt",
  "recovery_strategy": "Use set_antidetection with respect_robots_txt=false...",
  "details": {"url": "..."}
}
```

**Common Error Codes:**
- `INVALID_URL` - URL format error
- `FETCH_ERROR` - Failed to fetch page
- `ROBOTS_BLOCKED` - Blocked by robots.txt
- `EXTRACTION_ERROR` - Failed to extract content
- `INVALID_PROFILE` - Unknown anti-detection profile

## Project Structure

```
app/
  auth/           # JWT authentication middleware
  errors/         # Error mapping with recovery strategies
  exceptions/     # Custom exception hierarchy
  logger/         # Session-aware logging
  mcp_server/     # MCP tool implementations
  scraping/       # Web scraping components
    anti_detection.py   # Anti-detection profiles
    extractor.py        # Content extraction
    fetcher.py          # HTTP requests
    robots.py           # robots.txt parsing
    structure.py        # Page structure analysis
  config.py       # Configuration management
  main_mcp.py     # MCP server entry point
docker/           # Docker development environment
scripts/          # Utility scripts
test/             # Test suite (250+ tests)
docs/             # Documentation
```

## Configuration

Environment variables:
- `GOFR_DIG_DATA_DIR` - Data directory path
- `GOFR_DIG_JWT_SECRET` - JWT secret for authentication
- `GOFR_DIG_TOKEN_STORE` - Path to token store file

## Development

```bash
# Run tests
./scripts/run_tests.sh

# Run specific test file
uv run pytest test/mcp/test_get_content.py -v

# Check code quality
uv run ruff check app/ test/
uv run pyright app/
```

## License

See [LICENSE](LICENSE) file.
