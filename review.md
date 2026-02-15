# Documentation Review: gofr-dig

**Review Date:** February 14, 2026
**Reviewer:** GitHub Copilot

## 1. Top-Level README
**Status:** ✅ Accurate and functional.
- Provides a clear functional overview.
- Links to detailed documentation are correct.
- "Quick Start" commands match the `scripts/` directory contents.
- **Recommendations:**
  - Add a direct link to `docs/news_parser.md` in the "Documentation" table, as it is a significant feature not currently listed there (though it is mentioned in the text).
  - Explicitly mention that `scripts/bootstrap_gofr_dig.sh` should be run *before* `start-prod.sh` in the "Quick Start" section for new users, matching `getting_started.md`.

## 2.1. System Architecture (`docs/architecture.md`)
**Status:** ✅ Accurate but high-level.
- Correctly identifies the three main services (MCP, MCPO, Web) and their purposes.
- Mentions ports 8070, 8071, 8072 which matches `docker/compose.prod.yml` and `app/web_server/web_server.py`.
- Describes the scraping and session flow correctly.
- **Recommendations:**
  - Could benefit from a diagram (Mermaid) to visualize the flow between Agent -> MCP -> Scraping Engine -> Session Storage -> Web Server.
  - Mention `lib/gofr-common` as a dependency for core utilities (auth, logging, config) to match the project structure.

## 2.2. Tools API (`docs/tools.md`)
**Status:** ⚠️ Mostly accurate, but missing `auth_token` details in some tool descriptions vs schemas.
- **Tools Verified:**
  - `ping`: code ✅ / docs ✅
  - `set_antidetection`: code ✅ / docs ✅. **Note:** Docs mention `custom_user_agent` but code schema has it too.
  - `get_content`: code ✅ / docs ✅. **Discrepancy:** Docs say default `max_pages_per_level` is 5, code schema says 5. Checked out.
  - `get_structure`: code ✅ / docs ✅
  - `get_session_info`: code ✅ / docs ✅
  - `get_session_chunk`: code ✅ / docs ✅
  - `list_sessions`: code ✅ / docs ✅
  - `get_session_urls`: code ✅ / docs ✅
  - `get_session`: code ✅ / docs ✅
- **Discrepancies:**
  - The `auth_token` parameter is present in the code schema for ALL tools (added via `**AUTH_TOKEN_SCHEMA`), but the documentation for some tools (like `ping`, `set_antidetection` in the description text) doesn't always explicitly list it as a parameter in the *markdown table* for every single tool, though it is often mentioned. *Correction: logic check - tools.md actually does list `auth_token` in the tables for `set_antidetection`, `get_content`, etc. It seems consistent.*
  - **Correction:** `ping` does *not* take `auth_token` in the docs table, but `handle_list_tools` code for `ping` has `inputSchema={"type": "object", "properties": {}}` so it takes NO arguments. The docs are correct (`Parameters: none`).
  - **Findings:** The documentation is remarkably accurate and auto-generated-like in quality.

## 2.3. Scraping & Parsing (`docs/news_parser.md`, `docs/source_profiles.md`)
**Status:** ✅ High quality and accurate.
- `news_parser.md` spec matches the implemented `parse_results` logic in `get_content`.
- `source_profiles.md` accurately describes the `SOURCE_PROFILES` dictionary in `app/processing/source_profiles.py`.
- CODE CHECK: `app/processing/source_profiles.py` contains `scmp` and `generic` profiles, matching the docs.
- **Recommendations:**
  - None. These are excellent deep-dive documents.

## 2.4. Workflow (`docs/workflow.md`)
**Status:** ✅ accurate.
- Covers the standard loop: Configure -> Discover -> Extract -> Retrieve.
- **Recommendations:**
  - Add a section on "Authentication" explaining how to get a token and pass it, as the system seems to be moving towards mandatory auth (referenced in `start-prod.sh --no-auth` warnings).

## 2.5. Getting Started & Integrations (`docs/getting_started.md`)
**Status:** ⚠️ Valid, but N8N/OpenWebUI sections requested by user are MISSING from the file explicitly, though implied in README.
- The user request asked for "getting started + N8N + OpenWebUI integration".
- **Current State:** `getting_started.md` covers Docker and installation. It *links* to `workflow.md`. It does *not* have specific N8N or OpenWebUI integration guides.
- **Gap analysis:**
  - The `README.md` has a small section on "Connect N8N to gofr-dig".
  - There is a file `n8n/GOFR-DIG-MCP-Workflow.json` which is the actual workflow integration, but it is not referenced in `getting_started.md`.
  - OpenWebUI integration is mentioned in the user prompt ("N8N + OpenWebUI integration") but I found no specific docs or config files for OpenWebUI in the file tree (except potentially generic MCP support).

## Action Plan
1.  **Update `docs/getting_started.md`:**
    - Add a new section **"Integration with AI Platforms"**.
    - **N8N:** Move/expand the N8N instructions from README to here. Reference `n8n/GOFR-DIG-MCP-Workflow.json`.
    - **OpenWebUI:** Add instructions for OpenWebUI (Connect via HTTP/MCP). Since `gofr-dig` exposes a standard MCP endpoint (`/mcp` on port 8070) and an SSE endpoint, it should work with OpenWebUI's MCP client support if available, or via generic HTTP tools. *Self-correction: OpenWebUI supports standard MCP. I will assume standard MCP connection instructions apply.*
2.  **Update `README.md`:**
    - Shorten the N8N section and link to the new detailed `getting_started.md` section to reduce duplication.
    - Add `docs/news_parser.md` to the documentation table.
