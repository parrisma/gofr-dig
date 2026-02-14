# gofr-dig

**Web scraping for AI agents.** gofr-dig is an MCP server that lets LLMs and automation services fetch, extract, and paginate web content — with anti-detection, robots.txt compliance, and session-based chunking for large results.

## Accessing N8N, OPenWebUI
When N8N and OPenwebUi are run in dev container, find the IP of teh docker host and use that in teh URL NOT localhost

$ ip route | awk '/default/ {print $3}'
172.22.0.1

so N8N in chrome = http://172.22.0.1:8084/setup

## Connect N8N to gofr-dig (MCP)
1. In N8N, open your workflow view and click the + button (top right).
2. Search for and add an MCP Client node.
3. Set Transport to HTTP Streamable.
4. Set MCP Endpoint URL to one of these (note the trailing slash):
  - http://gofr-dig-mcp:8070/mcp/
  - http://localhost:8070/mcp/
5. In Tool, choose From List and select the gofr-dig tool (a quick test is ping).

## What It Does

| Capability | Description |
|---|---|
| **Content extraction** | Fetch a page and get clean text, links, headings, images, and metadata |
| **Recursive crawling** | Follow links up to 3 levels deep to scrape documentation sites |
| **Structure analysis** | Inspect page layout, navigation, forms, and heading outline — without extracting full text |
| **Anti-detection** | Configurable profiles (stealth, balanced, browser TLS) to avoid bot blocking |
| **Session storage** | Large results are stored server-side and retrieved in chunks via session ID |
| **REST API** | Every session chunk is also available as a plain HTTP GET for automation fan-out |

## Quick Start

### Docker (recommended)

```bash
# Start production stack (MCP :8070, MCPO :8071, Web :8072)
./scripts/start-prod.sh

# Without authentication
./scripts/start-prod.sh --no-auth

# Stop
./scripts/start-prod.sh --down
```

### Local development

```bash
uv sync
uv run python -m app.main_mcp --host 0.0.0.0 --port 8070
```

## How It Works

```
LLM / Agent                              gofr-dig
                            ─────────

set_antidetection(profile="balanced")  →  Configure headers & rate limit
get_structure(url)                     →  Page layout, selectors, outline
get_content(url, depth=2)              →  Crawl → store → return session_id
get_session_chunk(session_id, 0)       →  Chunk 0 text
get_session_chunk(session_id, 1)       →  Chunk 1 text
  ...                                     ...
```

Multi-page crawls (depth > 1) automatically store results in a session and return a `session_id` with chunk metadata. Single-page fetches return content inline by default, or as a session if `session=true` is passed.

## MCP Tools

| Tool | Purpose |
|---|---|
| `ping` | Health check |
| `set_antidetection` | Configure scraping profile, rate limits, robots.txt |
| `get_content` | Fetch and extract page text (single page or recursive crawl) |
| `get_structure` | Analyze page layout and discover CSS selectors |
| `get_session_info` | Get session metadata (chunk count, size, URL) |
| `get_session_chunk` | Retrieve one chunk of stored content |
| `list_sessions` | Browse all stored sessions |
| `get_session_urls` | Get HTTP URLs for every chunk (automation fan-out) |

Full parameter reference: [docs/TOOLS.md](docs/TOOLS.md)

## Documentation

| Document | Contents |
|---|---|
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Step-by-step usage guide with examples |
| [docs/TOOLS.md](docs/TOOLS.md) | Complete MCP tool reference (parameters, returns, errors) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Technical internals, error handling, scraping pipeline |

## Services

| Service | Default Port | Entry Point | Protocol |
|---|---|---|---|
| MCP Server | 8070 | `app.main_mcp` | MCP (Streamable HTTP) |
| MCPO Server | 8071 | `app.main_mcpo` | OpenAPI wrapper over MCP |
| Web Server | 8072 | `app.main_web` | REST API (sessions, health) |

Ports are configured in `lib/gofr-common/config/gofr_ports.env`.

## Project Structure

```
app/
  mcp_server/      MCP tool schemas and handlers
  web_server/      REST API (session endpoints, health)
  scraping/        Fetcher, extractor, structure analyzer, anti-detection, robots.txt
  session/         Session manager (chunked storage)
  errors/          Error mapper with recovery strategies
  exceptions/      Typed exception hierarchy
  logger/          Session-aware structured logging
  startup/         Boot-time validation
  config.py        Configuration (paths, env vars)
  main_mcp.py      MCP server entry point
  main_mcpo.py     MCPO (OpenAPI) entry point
  main_web.py      Web server entry point
docker/            Compose files, Dockerfiles, launcher scripts
test/              pytest suite (300+ tests)
docs/              Workflow, tools reference, architecture
scripts/           Test runner, backup, token management
```

## Development

```bash
# Run all tests
./scripts/run_tests.sh

# Run MCP tests only
uv run pytest test/mcp/ -v

# Code quality
uv run ruff check app/ test/
```

## License

See [LICENSE](LICENSE).
