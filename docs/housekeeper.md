# Housekeeper Service

A new background service has been added to `gofr-dig` to manage storage usage automatically.

## Purpose

The Housekeeper service ensures that the disk space used by stored sessions does not exceed a configured limit. It runs periodically and deletes the oldest sessions first until usage is below the threshold.

## Configuration

The service is configured via environment variables in `docker/compose.prod.yml`:

For local/operator defaults, set these in `scripts/gofr-dig.env` so scripts and compose usage stay aligned.

| Variable | Default | Description |
|---|---|---|
| `GOFR_DIG_HOUSEKEEPING_INTERVAL_MINS` | `60` | Frequency of checks in minutes. |
| `GOFR_DIG_MAX_STORAGE_MB` | `1024` | Maximum storage usage in MiB. |
| `GOFR_DIG_HOUSEKEEPER_LOCK_STALE_SECONDS` | `3600` | Stale lock timeout for prune concurrency control. |
| `GOFR_DIG_STORAGE` | (auto) | Path to storage directory (handled by defaults). |

## Behavior

1.  Calculates total size of all stored sessions (including metadata and blobs).
2.  Sorts sessions by creation time (ascending).
3.  Uses a lock file (`.prune_size.lock`) to ensure only one prune run is active.
4.  If total size > `MAX_STORAGE_MB`:
    *   Deletes oldest sessions one by one.
    *   Logs each deletion to `gofr-dig-housekeeper.log` (JSON format) and stdout.
    *   Stops when total size <= limit.
5.  If target cannot be reached (for example, metadata anomalies), emits a warning and exits that cycle with non-zero status.

## Manual Usage

You can also run the pruning logic manually via the CLI:

```bash
# Prune until size is < 500 MB
./scripts/storage_manager.sh prune-size --max-mb 500

# With verbose output
./scripts/storage_manager.sh prune-size --max-mb 500 --verbose
```

## Logs

Logs are written to `logs/gofr-dig-housekeeper.log` and are ingested by SEQ if configured.
Look for `logger="housekeeper"` events.

Storage manager CLI operations are also emitted to SEQ via core structured logging.
Key events include:

- `storage_manager.command_start`
- `storage_manager.command_end`
- `storage_manager.prune.check`
- `storage_manager.prune.summary`
- `storage_manager.prune.validation_failed`
- `storage_manager.prune.lock_busy`
