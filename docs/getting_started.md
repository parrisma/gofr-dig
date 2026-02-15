# Getting Started

This guide explains how to install, run, and integrate `gofr-dig`.

## Prerequisites

*   **Docker Desktop (or Engine)**: For running the services.
*   **Git**: For downloading the code.
*   **Linux/Mac**: Recommended. Windows users should use WSL2.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository_url> gofr-dig
    cd gofr-dig
    ```

2.  **Run the Bootstrap Script**:
    This sets up secure credentials, networks, and builds the Docker images.
    ```bash
    ./scripts/bootstrap_gofr_dig.sh
    ```

## Running the Application

### Production Mode (Recommended)

Start the full stack (MCP server, API, Documentation, etc.) in detached mode:

```bash
./scripts/start-prod.sh
```

To stop:
```bash
./scripts/start-prod.sh --down
```

### Development Mode

For contributing code or running tests:

```bash
./scripts/run-dev-container.sh
```

## Integrations

### 1. N8N Integration

`gofr-dig` works natively with N8N's MCP Client node.

**Prerequisite:** Ensure `gofr-dig` and `n8n` are on the same Docker network, or use the host IP.
If running N8N in Docker, use the host IP: `http://172.17.0.1:8070/mcp/` (check your flexible IP).

1.  **Add MCP Client Node**: In your N8N workflow, add an **MCP Client** node.
2.  **Configure Transport**:
    *   **Transport**: `HTTP Streamable` (SSE)
    *   **MCP Endpoint URL**: `http://gofr-dig-mcp:8070/mcp/` (if using internal Docker DNS) or `http://localhost:8070/mcp/` (if using host networking).
3.  **Select Tool**:
    *   Click "Fetch Tools".
    *   Select `get_content` or `get_structure` from the list.

**Example Workflow:**
An example workflow handling pagination and session retrieval is available in `n8n/GOFR-DIG-MCP-Workflow.json`. Import this file into N8N to see a complete pattern.

### 2. OpenWebUI Integration

Connecting `gofr-dig` to OpenWebUI allows LLMs in your chat interface to browse the web using our tools.

1.  **Open Settings**: Go to **Admin Panel** > **Settings** > **Tools** (or **Functions**).
2.  **Add MCP Server**:
    *   **Name**: `gofr-dig`
    *   **Type**: `SSE` (Server-Sent Events)
    *   **URL**: `http://host.docker.internal:8070/mcp/` (or your server's IP).
3.  **Verify**:
    *   Click the verify/connect button. You should see tools like `get_content`, `get_structure` appear.
4.  **Usage**:
    *   In a chat, type `@gofr-dig` or simply ask the model to "scrape this URL" and it will invoke the tool automatically.

## Next Steps

*   **[Functional Overview](../README.md)**: What the system does.
*   **[Workflow Guide](workflow.md)**: How to combine tools for complex tasks.
*   **[Tool Reference](tools.md)**: Detailed parameter list.

