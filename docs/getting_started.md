# Getting Started

This guide covers how to set up `gofr-dig` on a new machine.

## Prerequisites

Ensure you have the following installed:
*   **Git**: For downloading the code.
*   **Docker Desktop (or Engine)**: For running the services and database.

## Installation

We provide a single script that sets up everything (databases, keys, networks, and containers).

1.  **Download the code**:

    ```bash
    git clone <repository_url> gofr-dig
    cd gofr-dig
    ```

2.  **Run the Setup Script**:

    ```bash
    ./scripts/bootstrap_gofr_dig.sh
    ```
    
    *This creates all necessary Docker images, networks, and secure credentials.*

## Running the Application

### Development Mode

Good for coding and testing changes.

```bash
./docker/run-dev.sh
```

### Production Mode

Good for running the service for actual use.

```bash
./docker/start-prod.sh
```

*(To stop the production service, run `./docker/start-prod.sh --down`)*

## Verifying It Works

Once running, you can check the health of the service:

```bash
curl http://localhost:8072/health
```

## Next Steps

*   Learn how to use the tools in the **[Workflow Guide](workflow.md)**.
*   See the list of available commands in **[Tool Reference](tools.md)**.
*   Understand the system design in **[Architecture](architecture.md)**.
