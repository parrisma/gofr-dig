# Implementation Plan: parse_results Flag for get_content

## Summary

Add a `parse_results` boolean parameter to the `get_content` MCP tool (and align the web layer).
When `true` (the default), the server runs the deterministic `NewsParser` on the crawl result
before returning it, so callers receive a structured feed of stories, deduplication,
provenance, and parse-quality signals.  When `false`, the raw crawl output is returned
unchanged (current behavior).

When `parse_results=true` the parser ALWAYS runs — regardless of depth.  For depth=1
the handler wraps the single-page result into the `{start_url, pages: [page]}` shape the
parser expects.  There is no special-casing or silent ignoring.


## Current State

- `get_content` returns raw crawl data: a dict with `pages[]`, `summary`, `start_url`, etc.
- `NewsParser` exists in `app/processing/news_parser.py` and accepts an input dict that
  already matches the multi-page crawl result shape (`start_url`, `pages`, optional
  `crawl_time_utc`, `parser_version`, `source_profile_name`).
- The web server (`app/web_server/web_server.py`) exposes session-retrieval endpoints only;
  it does not perform scraping or parsing of its own.


## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Default value | `true` | The whole point of the parser is to run automatically. Callers who want raw data opt out explicitly. |
| Depth-1 behavior | Always parse | When `parse_results=true` the handler wraps the single-page result into `{start_url, pages: [page]}` so the parser runs regardless of depth. |
| Session interaction | Parse runs BEFORE session storage | The session stores whichever payload the caller receives (parsed or raw). Parsed output is smaller and more useful for downstream consumers. |
| Error handling | Parser failures return `PARSE_ERROR` | New error code; if the parser throws, we catch it and return a structured error. The raw result is NOT returned as fallback — if the caller asked for parsed output and parsing fails, that is an error. |
| Web alignment | Session content reflects whatever was stored | If the content was stored parsed, sessions serve parsed content. The web layer needs no code change — it retrieves stored sessions regardless of how they were created. |


## Detailed Changes

### 1. MCP Tool Schema — `handle_list_tools` (mcp_server.py)

Add `parse_results` to the `get_content` inputSchema.properties:

    "parse_results": {
        "type": "boolean",
        "description": (
            "Run the deterministic news parser on crawl results. "
            "Returns a structured feed with deduplicated stories, sections, "
            "provenance, and parse-quality signals instead of raw page data. "
            "Applies to all depths. Default true."
        ),
        "default": True,
    }

Update the tool description text to mention the flag:

    Add to SESSION MODE section or add a new PARSE MODE section:
    "PARSE MODE:\n"
    "- parse_results=true (default): multi-page crawl results are processed by the "
    "deterministic news parser. Returns structured stories with dedup, classification, "
    "and parse quality signals.\n"
    "- parse_results=false: returns raw crawl output (pages, text, links, etc).\n"
    "- Only applies when depth >= 2. Ignored for single-page fetches.\n\n"


### 2. MCP Handler — `_handle_get_content` (mcp_server.py)

At the argument-extraction section (around line 1100):

    parse_results = arguments.get("parse_results", True)

After the multi-page crawl completes (around line 1490, after depth-3 block, before session/truncation):

    if parse_results:
        try:
            from app.processing.news_parser import NewsParser
            from datetime import datetime, timezone

            # Wrap depth-1 result into parser-expected shape
            if depth == 1:
                results = {
                    "start_url": url,
                    "pages": [results],
                }

            # Inject crawl metadata the parser needs
            results["crawl_time_utc"] = crawl_time_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            results["parser_version"] = "1.0.0"
            # source_profile_name is optional; caller can pass it as an argument
            if source_profile_name:
                results["source_profile_name"] = source_profile_name

            parser = NewsParser()
            parsed = parser.parse(results)

            # Replace the raw crawl result with the parsed feed
            # Keep original summary and crawl metadata for reference
            parsed["raw_summary"] = results.get("summary")
            parsed["crawl_depth"] = depth
            parsed["response_type"] = results.get("response_type", "inline")
            results = parsed

        except Exception as exc:
            logger.error(
                "news_parser_failed",
                error=str(exc),
                url=url,
                depth=depth,
            )
            return _error_response(
                "PARSE_ERROR",
                f"News parser failed: {exc}",
                {"url": url, "depth": depth},
            )

For multi-page crawls (depth >= 2) the `results` dict already has the shape the parser
expects (`start_url`, `pages[]`).  For depth=1 the handler must wrap the single-page
result before calling the parser:

    # Wrap depth-1 result into parser-expected shape
    if depth == 1:
        results = {
            "start_url": url,
            "pages": [results],
        }

Additional fields the parser looks for:
- `crawl_time_utc` — must be injected (the MCP handler tracks crawl start time but doesn't write it to the dict today)
- `parser_version` — hardcoded "1.0.0"
- `source_profile_name` — optional new argument (see step 3)


### 3. New Optional Argument: `source_profile_name` (mcp_server.py)

Add to get_content inputSchema.properties:

    "source_profile_name": {
        "type": "string",
        "description": (
            "Source profile for the news parser (e.g. 'scmp'). "
            "Controls site-specific date patterns, section labels, and noise markers. "
            "Omit to use the generic fallback profile. "
            "Only used when parse_results=true."
        ),
    }

At the argument-extraction section:

    source_profile_name = arguments.get("source_profile_name")

This is pass-through only; the parser does the lookup via `get_source_profile()`.


### 4. Inject `crawl_time_utc` into result dict (mcp_server.py)

At the start of the multi-page crawl block (around line 1365), record crawl start time:

    from datetime import datetime, timezone
    crawl_time_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

Then inject it into the results dict before parsing:

    results["crawl_time_utc"] = crawl_time_utc


### 5. New Error Code: `PARSE_ERROR` (mapper.py)

Add to RECOVERY_STRATEGIES:

    "PARSE_ERROR": (
        "The news parser failed to process the crawl results. "
        "Retry with parse_results=false to get raw output, or check "
        "source_profile_name for the target site."
    ),


### 6. Web Alignment

The web server (`app/web_server/web_server.py`) currently only serves sessions — it does not
perform scraping or content fetching.  Session content is whatever was stored by the MCP layer.

No code changes needed in the web server:
- If a session was created with parse_results=true, the session stores the parsed feed.
- If it was created with parse_results=false, the session stores raw crawl data.
- Session-retrieval endpoints (info, chunks, urls) are format-agnostic.

The alignment is automatic because the MCP layer is the single point where parsing happens
BEFORE storage.


### 7. Documentation Updates

#### docs/tools.md

- Add `parse_results` and `source_profile_name` parameters to `get_content` section.
- Add `PARSE_ERROR` to the error table.
- Add a "Parse Mode" subsection under Behavior Notes explaining what the parser does.

#### docs/workflow.md

- Mention that multi-page crawls automatically produce parsed output by default.
- Add example workflow showing depth=2 with parse_results for news analysis.


### 8. Tests

#### test/mcp/test_parse_results_flag.py (new)

    test_parse_results_true_returns_feed_meta
        - Mock crawl output matching multi-page shape.
        - Verify result has feed_meta, stories, no raw pages[].

    test_parse_results_false_returns_raw
        - Same crawl, parse_results=false.
        - Verify result has pages[], summary, no feed_meta.

    test_parse_results_works_for_depth_1
        - depth=1, parse_results=true.
        - Verify result has feed_meta and stories (parser ran on wrapped single page).

    test_parse_error_returns_error_code
        - Craft input that causes parser to throw (e.g. missing pages).
        - Verify PARSE_ERROR error code.

    test_parse_results_with_session_stores_parsed
        - parse_results=true, session=true.
        - Create session → get_session_info → get_chunk.
        - Verify chunk content is from the parsed feed.

    test_source_profile_name_passed_through
        - parse_results=true, source_profile_name="scmp".
        - Verify feed_meta.source_profile == "scmp".

#### test/processing/test_news_parser.py (extend)

    test_parser_accepts_raw_mcp_crawl_shape
        - Feed a dict with the exact shape _handle_get_content produces for depth=2.
        - Verify no CrawlInputError.
        - This is a contract test to catch MCP → parser shape drift.


## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `app/mcp_server/mcp_server.py` | Modify | Add `parse_results` + `source_profile_name` to schema, inject `crawl_time_utc`, call parser after crawl |
| `app/errors/mapper.py` | Modify | Add `PARSE_ERROR` recovery strategy |
| `docs/tools.md` | Modify | Add new params, error code, behavior note |
| `docs/workflow.md` | Modify | Add parse-mode workflow example |
| `test/mcp/test_parse_results_flag.py` | New | Integration tests for the flag |
| `test/processing/test_news_parser.py` | Modify | Contract test for MCP output shape |


## Execution Order

1. ~~Add `PARSE_ERROR` to `app/errors/mapper.py` + add to the known-keys set in the
   recovery-strategy coverage test.~~ **DONE**
2. ~~Add `parse_results` and `source_profile_name` to MCP tool schema.~~ **DONE**
3. ~~Add argument extraction + crawl_time_utc injection + parser call in `_handle_get_content`.~~ **DONE**
4. ~~Write tests, run `./scripts/run_tests.sh --unit`.~~ **DONE** — 466 passed, 33 deselected
5. ~~Update `docs/workflow.md` with parse-mode workflow example.~~ **DONE**
6. Rebuild prod: `./scripts/start-prod.sh --build`. (manual step)
7. ~~Rewrite `docs/tools.md` from scratch to reflect the actual code~~ **DONE** — read every Tool()
   definition and RECOVERY_STRATEGIES key from the codebase and produce an authoritative
   reference that matches the live implementation. This is the final step because it
   captures everything added in steps 1-6 plus any pre-existing drift between
   code and docs.


## Rollback

Set `parse_results` default to `false` in the schema if callers report issues.
The parser module stays in the codebase either way; it becomes opt-in instead of opt-out.
