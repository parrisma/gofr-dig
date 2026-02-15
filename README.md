# gofr-dig

**Web scraping for AI agents.** gofr-dig is an MCP server that lets LLMs and automation services fetch, extract, and paginate web content — with anti-detection, robots.txt compliance, and session-based chunking for large results.

## Accessing N8N, OpenWebUI
See **[Getting Started](docs/getting_started.md)** for detailed integration guides for N8N and OpenWebUI.

## New Machine TL;DR

```bash
git submodule update --init --recursive
./scripts/bootstrap_gofr_dig.sh --yes
./lib/gofr-common/scripts/bootstrap_seq.sh
./scripts/start-prod.sh
./lib/gofr-common/scripts/auth_manager.sh --docker groups list
./scripts/run_tests.sh
```

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

### 1. One-time Setup
```bash
./scripts/bootstrap_gofr_dig.sh
```

### 2. Run Production
```bash
# Start production stack (MCP :8070, MCPO :8071, Web :8072)
./scripts/start-prod.sh
```

### 3. Verification
```bash
curl http://localhost:8072/health
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
| `get_session` | Retrieve full content from a session (concatenated) |

Full parameter reference: [docs/tools.md](docs/tools.md)

## Documentation

| Document | Contents |
|---|---|
| [docs/getting_started.md](docs/getting_started.md) | **Start Here**. Installation, usage, and N8N/OpenWebUI integration. |
| [docs/workflow.md](docs/workflow.md) | Step-by-step usage guide with examples. |
| [docs/tools.md](docs/tools.md) | Complete MCP tool reference (parameters, returns, errors). |
| [docs/news_parser.md](docs/news_parser.md) | Deep dive into the deterministic news parser and post-processing. |
| [docs/architecture.md](docs/architecture.md) | Technical internals, error handling, scraping pipeline. |

## Quick Start

### 1. One-time Setup

