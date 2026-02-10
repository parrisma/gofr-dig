# Architecture

This document describes how `gofr-dig` works under the hood.

## System Overview

The system consists of three main parts:

1.  **MCP Server**: Handles requests from AI agents.
2.  **Scraping Engine**: Fetches and processes web pages.
3.  **Session Manager**: Stores large results so they don't overwhelm the client.

## How Scraping Works

When you request a page:

1.  **Check Rules**: The system checks `robots.txt` and anti-detection settings.
2.  **Fetch**: It downloads the page using a web browser simulation.
3.  **Extract**: It cleans up the HTML to get just the useful text and data.
4.  **Crawl** (Optional): If depth is > 1, it finds links and repeats the process for them.
5.  **Store**: References to the text are saved to disk (`data/storage/sessions`).

## Data Storage

To handle large websites, we don't return everything at once.

*   **Sessions**: Group all pages from a single request.
*   **Chunks**: We split the data into manageable pieces (approx. 4000 characters).
*   **Retrieval**: Clients ask for specific chunks as needed.

## Services & Ports

*   **MCP Server** (Port 8070): The main tool interface.
*   **Web Server** (Port 8072): Provides direct access to session files.
