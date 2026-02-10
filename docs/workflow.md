# Workflow Guide

This guide explains the typical steps to use the `gofr-dig` web scraping tools.

For a complete list of parameters, see the **[Tool Reference](tools.md)**.

## Typical Process

1.  **Configure** (Optional): Set up anti-detection rules.
2.  **Discover**: finding out how a page is built.
3.  **Extract**: Getting the actual text and data.
4.  **Retrieve**: Downloading the results.

---

## 1. Configure Anti-Detection (Optional)

If a website blocks automated requests, you can change how `gofr-dig` identifies itself using `set_antidetection`.

**Common Settings:**

*   `"balanced"`: (Default) Works for most sites.
*   `"stealth"`: For sites with bot detection.
*   `"browser_tls"`: For difficult sites like Wikipedia or Cloudflare-protected pages.

**Example**:
```json
{
  "profile": "stealth"
}
```

---

## 2. Discover Page Structure

Before downloading everything, you can inspect a page to see its layout, sections, and navigation. This is handled by `get_structure`.

**Example**:
```json
{
  "url": "https://docs.example.com"
}
```

The result tells you what sections (IDs and Classes) exist, which helps you target specific content later.

---

## 3. Extract Content

Use `get_content` to download text.

### Single Page
Get the text from one page immediately.

```json
{
  "url": "https://example.com/article"
}
```

### Multiple Pages (Crawling)
Follow links to download a set of pages (e.g., specific documentation).

```json
{
  "url": "https://docs.example.com",
  "depth": 2
}
```

*   `depth`: How many clicks to follow away from the start page.

**Note**: Large results (like multi-page crawls) are stored as a **Session**. The tool will return a `session_id` instead of the full text.

---

## 4. Retrieve Session Results

If `get_content` returned a `session_id`, the data is saved on the server. You can retrieve it in pieces ("chunks").

1.  **Check Status**:
    Use `get_session_info` to see how many chunks exist.
    ```json
    {"session_id": "<your-session-id>"}
    ```

2.  **Get Data**:
    Use `get_session_chunk` to get each piece.
    ```json
    {"session_id": "<your-session-id>", "chunk_index": 0}
    ```
