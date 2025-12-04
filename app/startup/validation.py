"""Server startup validation and initialization utilities."""

from typing import List
from app.config import Config
from app.logger import Logger


def validate_data_directory_structure(logger: Logger) -> None:
    """
    Validate that the required data directory structure exists.
    Creates missing directories and logs warnings if needed.

    Args:
        logger: Logger instance for reporting status

    Raises:
        RuntimeError: If data directory root doesn't exist or can't be created
    """
    required_dirs = [
        ("sessions", "Session state persistence"),
        ("auth", "Authentication token storage"),
        ("storage", "Proxy-mode rendered document storage"),
        ("docs", "Document templates, fragments, and styles"),
    ]

    data_dir = Config.get_data_dir()

    # Verify data directory exists and is writable
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Data directory verified",
            path=str(data_dir),
        )
    except Exception as e:
        raise RuntimeError(f"Failed to access/create data directory at {data_dir}: {str(e)}") from e

    # Check and create required subdirectories
    missing_dirs: List[str] = []
    for subdir_name, description in required_dirs:
        subdir_path = data_dir / subdir_name
        try:
            subdir_path.mkdir(parents=True, exist_ok=True)
            logger.debug(
                "Verified directory exists",
                directory=subdir_name,
                path=str(subdir_path),
                description=description,
            )
        except Exception as e:
            missing_dirs.append(f"{subdir_name} ({description})")
            logger.warning(
                "Failed to create directory",
                directory=subdir_name,
                path=str(subdir_path),
                error=str(e),
            )

    if missing_dirs:
        error_msg = (
            "Failed to initialize required data directories:\n"
            + "\n".join(f"  - {d}" for d in missing_dirs)
            + f"\n\nData directory: {data_dir}\n"
            + "Please ensure the data directory is accessible and writable."
        )
        raise RuntimeError(error_msg)

    logger.info(
        "Data directory structure validated successfully",
        path=str(data_dir),
        subdirectories=[d[0] for d in required_dirs],
    )
