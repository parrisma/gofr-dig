
import time
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.management.storage_manager import prune_size
from app.logger import session_logger as logger


def _parse_positive_int_env(name: str, default: int, minimum: int = 1) -> int:
    """Parse positive integer environment value with fallback."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default

    try:
        value = int(raw)
        if value < minimum:
            raise ValueError(f"must be >= {minimum}")
        return value
    except Exception:
        logger.warning(
            "housekeeper.invalid_env",
            variable=name,
            provided_value=raw,
            default_value=default,
        )
        return default

class HousekeeperArgs:
    """Mock arguments object for prune_size function"""
    def __init__(self, max_mb, storage_dir=None, group=None):
        self.max_mb = max_mb
        self.storage_dir = storage_dir
        self.data_root = None
        self.group = group
        self.verbose = False
        self.lock_stale_seconds = _parse_positive_int_env(
            "GOFR_DIG_HOUSEKEEPER_LOCK_STALE_SECONDS", 3600, minimum=30
        )
        # prune_size expects args.group

def main():
    logger.info("Starting gofr-dig housekeeper service")
    
    while True:
        interval_mins = _parse_positive_int_env("GOFR_DIG_HOUSEKEEPING_INTERVAL_MINS", 60)
        max_mb = _parse_positive_int_env("GOFR_DIG_MAX_STORAGE_MB", 1024)
        storage_dir = os.environ.get("GOFR_DIG_STORAGE")

        try:
            logger.info(
                "housekeeper.cycle_start",
                interval_mins=interval_mins,
                max_mb=max_mb,
                storage_dir=storage_dir,
            )
            
            args = HousekeeperArgs(max_mb=max_mb, storage_dir=storage_dir)
            result = prune_size(args)
            
            if result != 0:
                logger.warning("housekeeper.cycle_nonzero", status=result)
            else:
                logger.info("housekeeper.cycle_ok")
                
        except Exception as e:
            logger.error("housekeeper.cycle_failed", error=str(e), cause=type(e).__name__)
            
        # Sleep
        sleep_seconds = max(1, interval_mins * 60)
        logger.info("housekeeper.sleep", sleep_seconds=sleep_seconds, interval_mins=interval_mins)
        time.sleep(sleep_seconds)

if __name__ == "__main__":
    main()
