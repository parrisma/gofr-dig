HOW JWT AUTH WORKS IN GOFR-IQ (for another gofr project's LLM)
================================================================

OVERVIEW
--------
gofr-iq uses JWT tokens for group-based access control. The key design
decision: tokens are passed as a TOOL CALL PARAMETER (auth_tokens), not
exclusively via HTTP Authorization headers. Both paths are supported, but
the tool parameter is the primary mechanism when calling through MCPO.


THE TWO AUTH PATHS
------------------

PATH A: auth_tokens tool parameter (MCPO / proxy path - most common)
  - Every MCP tool has an explicit parameter:
      auth_tokens: list[str] | None
  - Callers pass JWT token strings directly in the tool call JSON, e.g.:
      {"tool": "query_documents", "arguments": {"query": "...", "auth_tokens": ["eyJ..."]}}
  - This exists because the MCPO proxy (MCP-over-HTTP) does NOT reliably
    forward HTTP headers into individual MCP tool invocations.
  - The tokens are raw JWT strings (no "Bearer " prefix needed, though the
    code strips it if present).

PATH B: Authorization header (direct MCP calls)
  - An AuthHeaderMiddleware on the Starlette app captures the HTTP
    Authorization header and stores it in a Python ContextVar.
  - Tool functions can read it via get_auth_header_from_context().
  - This works for direct HTTP calls to the MCP server, but NOT through MCPO.

RESOLUTION PRIORITY (in resolve_permitted_groups()):
  1. If auth_tokens parameter is provided -> use those tokens
  2. Else -> check Authorization header from ContextVar
  3. If neither -> default to ["public"] group (anonymous read-only)


JWT TOKEN STRUCTURE
-------------------
Payload (HS256 signed):
{
    "jti": "<token UUID>",           -- unique token ID, stored in Vault
    "groups": ["admin", "apac-sales"], -- group names this token can access
    "iat": <issued_at>,
    "exp": <expiry>,
    "nbf": <not_before>,
    "aud": "<audience>",             -- optional
    "fp": "<fingerprint>"            -- optional, for extra verification
}

The JWT secret is stored in Vault at: secret/gofr/config/jwt-signing-secret
Algorithm: HS256


TOKEN VALIDATION
----------------
When a tool receives auth_tokens, here is what happens:

1. resolve_permitted_groups(auth_tokens=["eyJ..."]) is called
2. For each token in the list:
   a. auth_service.verify_token(token, require_store=True)
   b. JWT is decoded and signature verified with the shared HS256 secret
   c. Claims checked: exp, nbf, iat
   d. Token's jti is looked up in Vault backend -- must exist and be "active"
   e. Groups in JWT must match groups in Vault store
3. Groups from all valid tokens are unioned together
4. "public" is always added to the result
5. Group names are converted to UUIDs via get_group_uuids_by_names()
6. Storage queries filter by those group UUIDs


GROUP-BASED ACCESS CONTROL
---------------------------
- READ operations: all groups from token + "public" are used as query filter
- WRITE operations: primary group (first in token's groups list) tags new data
- ADMIN operations: requires "admin" in groups, checked by require_admin()

In Neo4j, the pattern looks like:
  MATCH (c:Client)-[:IN_GROUP]->(g:Group) WHERE g.guid IN $group_guids

In ChromaDB, documents have group_guid metadata for filtering.


THE MCPO PROXY LAYER
---------------------
MCPO (app/mcpo_server/) wraps the MCP server as REST/OpenAPI endpoints.
It has two auth layers:

1. Client -> MCPO: API key (GOFR_IQ_MCPO_API_KEY env var)
   - Simple shared secret for the HTTP layer

2. MCPO -> MCP: depends on mode
   - GOFR_IQ_MCPO_MODE=auth: MCPO passes a fixed JWT via --header flag
     to the underlying MCP server (this goes through AuthHeaderMiddleware)
   - GOFR_IQ_MCPO_MODE=public: no JWT passed, tools default to "public"
   - Either way, external callers can ALSO pass auth_tokens in tool params
     for fine-grained per-call auth


WHAT THIS MEANS FOR ANOTHER GOFR PROJECT
-----------------------------------------
If you are calling gofr-iq tools (e.g., via n8n, OpenWebUI, or another MCP
client), here is how to authenticate:

1. Get a JWT token:
   - From secrets/bootstrap_tokens.json (admin_token or public_token)
   - Or create one via auth_manager.sh: tokens create --groups GROUP --name NAME

2. Pass it in every tool call as auth_tokens parameter:
   {
     "auth_tokens": ["eyJhbGciOiJIUzI1NiIs..."]
   }

3. The token determines what data you can see/write based on its groups.

4. You do NOT need to set an Authorization header if you pass auth_tokens.
   The parameter approach is preferred because it works through all proxies.