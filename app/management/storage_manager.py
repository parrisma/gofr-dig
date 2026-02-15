#!/usr/bin/env python3
"""Storage Management CLI for gofr-dig

Command-line utility to manage stored sessions and data including purging old data,
listing sessions, and displaying storage statistics.
"""

import argparse
import sys
import os
import time
import math
from contextlib import suppress
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gofr_common.storage import FileStorage
from app.config import Config
from app.logger import session_logger as logger


def _log_command_start(command: str, storage_dir: str, group: Optional[str] = None) -> None:
    logger.info(
        "storage manager command start",
        event="storage_manager.command_start",
        command=command,
        storage_dir=storage_dir,
        group=group,
    )


def _log_command_end(command: str, status_code: int, storage_dir: str, group: Optional[str] = None) -> None:
    logger.info(
        "storage manager command end",
        event="storage_manager.command_end",
        command=command,
        status_code=status_code,
        storage_dir=storage_dir,
        group=group,
    )


def _acquire_prune_lock(storage_dir: str, stale_seconds: int) -> tuple[bool, Optional[int], str]:
    """Acquire exclusive prune lock file.

    Returns:
        (acquired, fd, lock_path)
    """
    lock_path = str(Path(storage_dir) / ".prune_size.lock")
    now = time.time()

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"pid={os.getpid()} started_at={int(now)}\n".encode("utf-8"))
        return True, fd, lock_path
    except FileExistsError:
        try:
            age = now - os.path.getmtime(lock_path)
            if age > stale_seconds:
                logger.warning(
                    "housekeeper.lock_stale",
                    lock_path=lock_path,
                    age_seconds=age,
                    stale_seconds=stale_seconds,
                )
                with suppress(FileNotFoundError):
                    os.unlink(lock_path)
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"pid={os.getpid()} started_at={int(now)}\n".encode("utf-8"))
                return True, fd, lock_path
        except Exception as exc:
            logger.warning(
                "housekeeper.lock_check_failed",
                lock_path=lock_path,
                error=str(exc),
            )

        logger.warning("housekeeper.lock_busy", lock_path=lock_path)
        return False, None, lock_path


def _release_prune_lock(fd: Optional[int], lock_path: str) -> None:
    """Release prune lock file."""
    if fd is not None:
        with suppress(Exception):
            os.close(fd)
    with suppress(FileNotFoundError):
        os.unlink(lock_path)


def resolve_storage_dir(cli_dir: Optional[str], data_root: Optional[str] = None) -> str:
    """
    Resolve storage directory with priority chain.

    Priority:
    1. CLI --storage-dir argument
    2. CLI --data-root argument (storage/ subdirectory)
    3. GOFR_DIG_STORAGE environment variable
    4. Config defaults
    """
    # Priority 1: --storage-dir argument
    if cli_dir:
        return cli_dir

    # Priority 2: --data-root points to data directory, storage/ is subdirectory
    if data_root:
        return str(Path(data_root) / "storage")

    # Priority 3: GOFR_DIG_STORAGE environment variable
    gofr_storage = os.environ.get("GOFR_DIG_STORAGE")
    if gofr_storage:
        return gofr_storage

    # Priority 4: Config defaults
    return str(Config.get_storage_dir())


def purge(args):
    """Purge storage older than specified age"""
    storage_dir = resolve_storage_dir(args.storage_dir, args.data_root)

    try:
        storage = FileStorage(storage_dir)
        
        current_count = len(storage.list(group=args.group))

        if args.age_days == 0:
            if args.group:
                msg = f"Purging ALL items in group '{args.group}'"
            else:
                msg = "Purging ALL items"
            logger.warning(
                "purge all requested",
                event="storage_manager.purge.confirmation_required",
                purge_scope=msg,
                current_item_count=current_count,
                group=args.group,
                storage_dir=storage_dir,
            )

            if not args.yes:
                response = input("Are you sure? (yes/no): ")
                if response.lower() != "yes":
                    logger.info(
                        "purge cancelled by user",
                        event="storage_manager.purge.cancelled",
                        group=args.group,
                        storage_dir=storage_dir,
                    )
                    return 0

        deleted = storage.purge(age_days=args.age_days, group=args.group)
        logger.info(
            "storage purge summary",
            event="storage_manager.purge.summary",
            storage_dir=storage_dir,
            group=args.group,
            age_days=args.age_days,
            deleted_count=deleted,
        )

        logger.info(
            "purge completed",
            event="storage_manager.purge.completed",
            deleted_count=deleted,
            group=args.group,
            storage_dir=storage_dir,
        )
        return 0

    except Exception as e:
        logger.error(
            "Storage purge failed",
            event="storage_manager.purge.failed",
            error=str(e),
            cause=type(e).__name__,
            storage_dir=storage_dir,
            group=args.group,
            age_days=args.age_days,
        )
        return 1


def prune_size(args):
    """Purge oldest items until total storage size is under limit"""
    storage_dir = resolve_storage_dir(args.storage_dir, args.data_root)
    max_mb = float(args.max_mb)
    lock_stale_seconds = int(getattr(args, "lock_stale_seconds", 3600))
    
    if not math.isfinite(max_mb) or max_mb <= 0:
        logger.warning(
            "invalid prune threshold",
            event="storage_manager.prune.validation_failed",
            reason="invalid_max_mb",
            max_mb=max_mb,
            storage_dir=storage_dir,
            group=args.group,
        )
        return 1

    if lock_stale_seconds <= 0:
        logger.warning(
            "invalid prune lock stale seconds",
            event="storage_manager.prune.validation_failed",
            reason="invalid_lock_stale_seconds",
            lock_stale_seconds=lock_stale_seconds,
            storage_dir=storage_dir,
            group=args.group,
        )
        return 1

    lock_fd: Optional[int] = None
    lock_path = ""
    try:
        acquired, lock_fd, lock_path = _acquire_prune_lock(storage_dir, lock_stale_seconds)
        if not acquired:
            logger.warning(
                "prune skipped due to active lock",
                event="storage_manager.prune.lock_busy",
                lock_path=lock_path,
                storage_dir=storage_dir,
                group=args.group,
            )
            return 2

        storage = FileStorage(storage_dir)
        # Note: list() returns raw list of GUIDs
        guids = storage.list(group=args.group)
        
        if not guids:
            logger.info(
                "prune skipped because storage is empty",
                event="storage_manager.prune.empty_storage",
                storage_dir=storage_dir,
                group=args.group,
            )
            return 0
            
        # Gather metadata for all items
        item_details = []
        total_size = 0
        anomaly_count = 0
        anomaly_bytes = 0
        
        for guid in guids:
            meta = storage.metadata_repo.get(guid)
            if meta:
                size = meta.size or 0
                created = meta.created_at or ""
                # Use (created, guid, size) for sorting
                # Handle missing created by using empty string (sorts first/oldest?)
                # Actually newer items have larger timestamps. Older items smaller.
                # Strings sort lexicographically. ISO timestamps work fine.
                item_details.append((created, guid, size))
                total_size += size
            else:
                orphan_size = 0
                for blob_path in Path(storage_dir).glob(f"{guid}.*"):
                    if blob_path.is_file():
                        with suppress(OSError):
                            orphan_size += blob_path.stat().st_size
                anomaly_count += 1
                anomaly_bytes += orphan_size
                total_size += orphan_size
                logger.warning(
                    "housekeeper.metadata_missing",
                    guid=guid,
                    estimated_size=orphan_size,
                    storage_dir=storage_dir,
                )
                
        # Sort by created_at ascending (oldest first)
        item_details.sort()
        
        target_size_bytes = max_mb * 1024 * 1024
        current_mb = total_size / (1024 * 1024)
        
        logger.info(
            "housekeeper.check",
            event="storage_manager.prune.check",
            current_mb=current_mb,
            target_mb=max_mb,
            item_count=len(guids),
            anomalies=anomaly_count,
            anomaly_mb=anomaly_bytes / (1024 * 1024),
            storage_dir=storage_dir,
        )
        logger.info(
            "prune usage check",
            event="storage_manager.prune.usage",
            storage_dir=storage_dir,
            current_mb=current_mb,
            target_mb=max_mb,
            group=args.group,
        )
        
        if total_size <= target_size_bytes:
            logger.info(
                "prune not required",
                event="storage_manager.prune.noop",
                storage_dir=storage_dir,
                current_mb=current_mb,
                target_mb=max_mb,
                group=args.group,
            )
            return 0
            
        logger.info(
            "prune started",
            event="storage_manager.prune.started",
            storage_dir=storage_dir,
            current_mb=current_mb,
            target_mb=max_mb,
            group=args.group,
        )
        
        deleted_count = 0
        deleted_bytes = 0
        
        # Iterate sorted list (oldest first)
        for created, guid, size in item_details:
            if total_size <= target_size_bytes:
                break
                
            try:
                # Use storage.delete() which handles permission checks if group passed
                # storage.delete(guid, group) returns bool
                if storage.delete(guid, group=args.group):
                    total_size -= size
                    deleted_bytes += size
                    deleted_count += 1
                    if args.verbose:
                        logger.info(
                            "prune item deleted (verbose)",
                            event="storage_manager.prune.deleted_verbose",
                            guid=guid,
                            size=size,
                            created=created,
                        )
                    logger.info(
                        "housekeeper.prune",
                        event="storage_manager.prune.deleted",
                        guid=guid,
                        size=size,
                        created=created,
                    )
            except Exception as e:
                logger.error(
                    "housekeeper.delete_failed",
                    event="storage_manager.prune.delete_failed",
                    guid=guid,
                    error=str(e),
                )
                
        final_mb = total_size / (1024 * 1024)
        logger.info(
            "prune completed",
            event="storage_manager.prune.completed",
            deleted_count=deleted_count,
            freed_mb=deleted_bytes / (1024 * 1024),
            final_mb=final_mb,
            group=args.group,
            storage_dir=storage_dir,
        )
        
        logger.info(
            "housekeeper.summary",
            event="storage_manager.prune.summary",
            item_count=len(guids),
            deleted_count=deleted_count,
            freed_mb=deleted_bytes / (1024 * 1024),
            final_mb=final_mb,
            target_mb=max_mb,
            anomalies=anomaly_count,
            exit_code=0,
        )

        if total_size > target_size_bytes:
            logger.warning(
                "housekeeper.target_unmet",
                event="storage_manager.prune.target_unmet",
                final_mb=final_mb,
                target_mb=max_mb,
                remaining_bytes=total_size - target_size_bytes,
                anomalies=anomaly_count,
                exit_code=1,
            )
            return 1

        return 0
        
    except Exception as e:
        logger.error(
            "Storage prune-size failed",
            event="storage_manager.prune.failed",
            error=str(e),
            cause=type(e).__name__,
            storage_dir=storage_dir,
            group=args.group,
            max_mb=max_mb,
        )
        return 1
    finally:
        _release_prune_lock(lock_fd, lock_path)


def list_items(args):
    """List stored items"""
    storage_dir = resolve_storage_dir(args.storage_dir, args.data_root)

    try:
        storage = FileStorage(storage_dir)
        items = storage.list(group=args.group)

        if not items:
            logger.info(
                "list found no items",
                event="storage_manager.list.empty",
                storage_dir=storage_dir,
                group=args.group,
            )
            return 0

        logger.info(
            "list items found",
            event="storage_manager.list.found",
            item_count=len(items),
            group=args.group,
            storage_dir=storage_dir,
            verbose=args.verbose,
        )

        if args.verbose:
            for guid in items:
                # Get metadata
                meta = storage.metadata_repo.get(guid)
                if meta:
                    fmt = meta.format or "?"
                    grp = meta.group or "none"
                    size = meta.size or 0
                    created = meta.created_at[:19] if meta.created_at else "N/A"
                else:
                    fmt = "?"
                    grp = "?"
                    size = 0
                    created = "N/A"

                logger.info(
                    "list item",
                    event="storage_manager.list.item",
                    guid=guid,
                    format=fmt,
                    group=grp,
                    size_bytes=size,
                    created=created,
                    storage_dir=storage_dir,
                )
        else:
            for guid in items:
                logger.info(
                    "list item guid",
                    event="storage_manager.list.item_guid",
                    guid=guid,
                    storage_dir=storage_dir,
                    group=args.group,
                )

        logger.info(
            "list summary",
            event="storage_manager.list.summary",
            storage_dir=storage_dir,
            group=args.group,
            item_count=len(items),
            verbose=args.verbose,
        )

        return 0

    except Exception as e:
        logger.error(
            "Failed to list storage items",
            event="storage_manager.list.failed",
            error=str(e),
            cause=type(e).__name__,
            storage_dir=storage_dir,
            group=args.group,
        )
        return 1


def stats(args):
    """Display storage statistics"""
    storage_dir = resolve_storage_dir(args.storage_dir, args.data_root)

    try:
        storage = FileStorage(storage_dir)
        items = storage.list(group=args.group)

        total_size = 0
        groups = {}

        for guid in items:
            meta = storage.metadata_repo.get(guid)
            if meta:
                size = meta.size or 0
                group = meta.group or "none"

                total_size += size
                groups[group] = groups.get(group, 0) + 1

        if groups:
            for group, count in sorted(groups.items()):
                logger.info(
                    "stats group entry",
                    event="storage_manager.stats.group",
                    group_name=group,
                    item_count=count,
                    storage_dir=storage_dir,
                )

        logger.info(
            "stats summary",
            event="storage_manager.stats.summary",
            storage_dir=storage_dir,
            group=args.group,
            item_count=len(items),
            total_size_bytes=total_size,
            group_count=len(groups),
        )

        return 0

    except Exception as e:
        logger.error(
            "Failed to get storage stats",
            event="storage_manager.stats.failed",
            error=str(e),
            cause=type(e).__name__,
            storage_dir=storage_dir,
            group=args.group,
        )
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="gofr-dig Storage Manager - Manage stored sessions and data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Purge items older than 30 days
  python -m app.management.storage_manager purge --age-days 30

  # Purge all items in 'test_group'
  python -m app.management.storage_manager purge --age-days 0 --group test_group --yes

    # Prune oldest items until storage is below 500 MB
    python -m app.management.storage_manager prune-size --max-mb 500

  # List all items with details
  python -m app.management.storage_manager list --verbose

  # Show storage statistics
  python -m app.management.storage_manager stats
        """,
    )

    # Global options
    parser.add_argument(
        "--gofr-dig-env",
        type=str,
        default=os.environ.get("GOFR_DIG_ENV", "TEST"),
        help="Environment mode (PROD/TEST)",
    )
    parser.add_argument(
        "--storage-dir",
        type=str,
        default=None,
        help="Storage directory (default: from config)",
    )
    parser.add_argument(
        "--data-root",
        type=str,
        default=None,
        help="Data root directory (storage will be subdirectory)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Purge command
    purge_parser = subparsers.add_parser("purge", help="Purge old items")
    purge_parser.add_argument(
        "--age-days",
        type=int,
        default=30,
        help="Delete items older than this many days (0 = delete all, default: 30)",
    )
    purge_parser.add_argument(
        "--group",
        type=str,
        default=None,
        help="Only purge items from this group",
    )
    purge_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

    # Prune-Size command
    prune_parser = subparsers.add_parser("prune-size", help="Delete oldest items until size < limit")
    prune_parser.add_argument(
        "--max-mb",
        type=float,
        required=True,
        help="Max storage size in MB (supports decimals)",
    )
    prune_parser.add_argument(
        "--group",
        type=str,
        default=None,
        help="Only prune items from this group",
    )
    prune_parser.add_argument(
        "--lock-stale-seconds",
        type=int,
        default=3600,
        help="Consider prune lock stale after this many seconds (default: 3600)",
    )
    prune_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print details of deleted items",
    )

    # List command
    list_parser = subparsers.add_parser("list", help="List stored items")
    list_parser.add_argument(
        "--group",
        type=str,
        default=None,
        help="Filter by group",
    )
    list_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed information",
    )

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show storage statistics")
    stats_parser.add_argument(
        "--group",
        type=str,
        default=None,
        help="Filter by group",
    )

    args = parser.parse_args()

    if args.command is None:
        logger.warning(
            "storage manager command missing",
            event="storage_manager.command_missing",
        )
        parser.print_help()
        return 0

    # Set environment
    os.environ["GOFR_DIG_ENV"] = args.gofr_dig_env

    command_to_group = {
        "purge": args.group,
        "prune-size": args.group,
        "list": args.group,
        "stats": args.group,
    }
    storage_dir = resolve_storage_dir(args.storage_dir, args.data_root)
    command = args.command
    _log_command_start(command=command, storage_dir=storage_dir, group=command_to_group.get(command))

    if args.command == "purge":
        status = purge(args)
    elif args.command == "prune-size":
        status = prune_size(args)
    elif args.command == "list":
        status = list_items(args)
    elif args.command == "stats":
        status = stats(args)
    else:
        logger.warning(
            "unknown storage manager command",
            event="storage_manager.command_unknown",
            command=args.command,
        )
        parser.print_help()
        status = 0

    _log_command_end(command=command, status_code=status, storage_dir=storage_dir, group=command_to_group.get(command))
    return status


if __name__ == "__main__":
    sys.exit(main())
