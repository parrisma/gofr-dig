import pytest
import json
import httpx
import os
from mcp import ClientSession
from mcp.client import streamable_http

streamable_http_client = streamable_http.streamablehttp_client

# Service URLs — prefer full URL env vars (set by run_tests.sh --docker/--no-docker),
# fall back to host+port construction for backwards compatibility.
MCP_URL = os.environ.get(
    "GOFR_DIG_MCP_URL",
    "http://{}:{}/mcp".format(
        os.environ.get("GOFR_DIG_HOST", "localhost"),
        os.environ.get("GOFR_DIG_MCP_PORT_TEST", "8170"),
    ),
)
WEB_URL = os.environ.get(
    "GOFR_DIG_WEB_URL",
    "http://{}:{}".format(
        os.environ.get("GOFR_DIG_HOST", "localhost"),
        os.environ.get("GOFR_DIG_WEB_PORT_TEST", "8172"),
    ),
)

def parse_json(result) -> dict:
    if result.content and len(result.content) > 0:
        text = result.content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"success": False, "error": text}
    return {"success": False, "error": "Empty response"}

class TestSessionFlow:
    """Integration test for the full session flow: Scrape -> MCP Chunks -> Web Chunks."""

    @pytest.mark.asyncio
    async def test_large_document_session_flow(self, html_fixture_server):
        """
        Test flow:
        1. Scrape a document into a session with small chunk size (forcing multiple chunks).
        2. Retrieve all chunks via MCP tools.
        3. Retrieve all chunks via Web endpoints.
        4. Verify content integrity.
        """
        base_url = html_fixture_server.base_url
        target_url = f"{base_url}/products.html"
        
        # We use a small chunk size to simulate a "large" document relative to the chunk size
        CHUNK_SIZE = 50

        async with streamable_http_client(MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # 1. Scrape into session
                print(f"\n[Step 1] Scraping {target_url} with chunk_size={CHUNK_SIZE}...")
                result = await session.call_tool(
                    "get_content", 
                    {
                        "url": target_url, 
                        "session": True,
                        "chunk_size": CHUNK_SIZE
                    }
                )
                response = parse_json(result)
                
                assert response["success"] is True
                assert "session_id" in response
                session_id = response["session_id"]
                total_chunks = response["total_chunks"]
                
                print(f"Session created: {session_id}")
                print(f"Total chunks: {total_chunks}")
                
                assert total_chunks > 1, "Should have multiple chunks with small chunk_size"

                # 2. Retrieve via MCP
                print("\n[Step 2] Retrieving chunks via MCP...")
                mcp_content = ""
                for i in range(total_chunks):
                    chunk_result = await session.call_tool(
                        "get_session_chunk",
                        {"session_id": session_id, "chunk_index": i}
                    )
                    # The tool returns the chunk text directly in the content
                    # Note: _json_text wraps the string in JSON quotes, so we need to load it
                    chunk_text_json = chunk_result.content[0].text  # type: ignore
                    chunk_text = json.loads(chunk_text_json)
                    mcp_content += chunk_text
                
                print(f"MCP retrieved {len(mcp_content)} chars.")

                # 3. Retrieve via Web
                print("\n[Step 3] Retrieving chunks via Web...")
                web_content = ""
                async with httpx.AsyncClient() as client:
                    # Check info first
                    info_resp = await client.get(f"{WEB_URL}/sessions/{session_id}/info")
                    assert info_resp.status_code == 200
                    info = info_resp.json()
                    assert info["session_id"] == session_id
                    assert info["total_chunks"] == total_chunks

                    # Fetch chunks
                    for i in range(total_chunks):
                        chunk_resp = await client.get(f"{WEB_URL}/sessions/{session_id}/chunks/{i}")
                        assert chunk_resp.status_code == 200
                        web_content += chunk_resp.text

                print(f"Web retrieved {len(web_content)} chars.")

                # 4. Verification
                assert mcp_content == web_content
                assert len(mcp_content) > 0
                assert "Products" in mcp_content  # Basic check that we got the right page
                
                print("\n[Success] Content matches between MCP and Web retrieval.")
