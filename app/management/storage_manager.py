#!/usr/bin/env python3
"""Storage Management CLI for gofr-dig

Command-line utility to manage stored sessions and data including purging old data,
listing sessions, and displaying storage statistics.
"""

import argparse
import sys
import os
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gofr_common.storage import FileStorage
from app.config import Config
from app.logger import session_logger as logger


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
            print(f"WARNING: {msg}")
            print(f"Current item count: {current_count}")

            if not args.yes:
                response = input("Are you sure? (yes/no): ")
                if response.lower() != "yes":
                    print("Purge cancelled.")
                    return 0

        deleted = storage.purge(age_days=args.age_days, group=args.group)

        print(f"Purge completed: {deleted} item(s) deleted")
        return 0

    except Exception as e:
        logger.error("Storage purge failed", error=str(e), cause=type(e).__name__)
        print(f"Error during purge: {str(e)}")
        return 1


def list_items(args):
    """List stored items"""
    storage_dir = resolve_storage_dir(args.storage_dir, args.data_root)

    try:
        storage = FileStorage(storage_dir)
        items = storage.list(group=args.group)

        if not items:
            print("No items found.")
            return 0

        print(f"{len(items)} Item(s) Found:")

        if args.verbose:
            print(f"{'GUID':<40} {'Format':<8} {'Group':<15} {'Size (bytes)':<12} {'Created'}")
            print("-" * 100)

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

                print(f"{guid:<40} {fmt:<8} {grp:<15} {size:<12} {created}")
        else:
            for guid in items:
                print(guid)

        return 0

    except Exception as e:
        logger.error("Failed to list storage items", error=str(e), cause=type(e).__name__)
        print(f"Error listing items: {str(e)}")
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

        group_filter = f" in group '{args.group}'" if args.group else ""
        print(f"Storage Statistics{group_filter}:")
        print(f"Total items:      {len(items)}")
        print(f"Total size:       {total_size:,} bytes ({total_size / (1024*1024):.2f} MB)")
        print(f"Storage dir:      {storage_dir}")

        if groups:
            print("Items by group:")
            for group, count in sorted(groups.items()):
                print(f"  {group:<15} {count:>5} items")

        return 0

    except Exception as e:
        logger.error("Failed to get storage stats", error=str(e), cause=type(e).__name__)
        print(f"Error getting stats: {str(e)}")
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
        parser.print_help()
        return 0

    # Set environment
    os.environ["GOFR_DIG_ENV"] = args.gofr_dig_env

    if args.command == "purge":
        return purge(args)
    elif args.command == "list":
        return list_items(args)
    elif args.command == "stats":
        return stats(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
