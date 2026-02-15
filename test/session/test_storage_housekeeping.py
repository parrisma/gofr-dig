from datetime import datetime, timedelta
from pathlib import Path

from gofr_common.storage import FileStorage

from app.housekeeper import _parse_positive_int_env
from app.management import storage_manager
from app.management.storage_manager import prune_size


class _Args:
    def __init__(self, storage_dir: Path, max_mb: float, lock_stale_seconds: int = 3600, group=None, verbose=False):
        self.storage_dir = str(storage_dir)
        self.data_root = None
        self.max_mb = max_mb
        self.group = group
        self.verbose = verbose
        self.lock_stale_seconds = lock_stale_seconds


def _set_created_at(storage: FileStorage, guid: str, created_at_iso: str) -> None:
    metadata = storage.metadata_repo.get(guid)
    assert metadata is not None
    metadata.created_at = created_at_iso
    storage.metadata_repo.save(metadata)


def test_parse_positive_int_env_uses_default_for_invalid(monkeypatch):
    monkeypatch.setenv("GOFR_DIG_HOUSEKEEPING_INTERVAL_MINS", "bad-value")
    assert _parse_positive_int_env("GOFR_DIG_HOUSEKEEPING_INTERVAL_MINS", 60) == 60

    monkeypatch.setenv("GOFR_DIG_HOUSEKEEPING_INTERVAL_MINS", "0")
    assert _parse_positive_int_env("GOFR_DIG_HOUSEKEEPING_INTERVAL_MINS", 60) == 60


def test_parse_positive_int_env_accepts_valid(monkeypatch):
    monkeypatch.setenv("GOFR_DIG_HOUSEKEEPING_INTERVAL_MINS", "15")
    assert _parse_positive_int_env("GOFR_DIG_HOUSEKEEPING_INTERVAL_MINS", 60) == 15


def test_prune_size_rejects_invalid_threshold(tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    args = _Args(storage_dir=storage_dir, max_mb=0)
    assert prune_size(args) == 1


def test_prune_size_deletes_oldest_first(tmp_path):
    storage_dir = tmp_path / "storage"
    storage = FileStorage(storage_dir)

    payload = b"x" * (24 * 1024)
    old_guid = storage.save(payload, format="json")
    mid_guid = storage.save(payload, format="json")
    new_guid = storage.save(payload, format="json")

    now = datetime.utcnow()
    _set_created_at(storage, old_guid, (now - timedelta(days=2)).isoformat())
    _set_created_at(storage, mid_guid, (now - timedelta(days=1)).isoformat())
    _set_created_at(storage, new_guid, now.isoformat())

    args = _Args(storage_dir=storage_dir, max_mb=0.05, verbose=True)
    result = prune_size(args)

    assert result == 0
    assert not storage.exists(old_guid)
    assert storage.exists(mid_guid)
    assert storage.exists(new_guid)


def test_prune_size_returns_busy_when_lock_exists(tmp_path):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    lock_file = storage_dir / ".prune_size.lock"
    lock_file.write_text("pid=1")

    args = _Args(storage_dir=storage_dir, max_mb=100, lock_stale_seconds=3600)
    assert prune_size(args) == 2


class _FakeLogger:
    def __init__(self):
        self.info_calls = []
        self.warning_calls = []
        self.error_calls = []

    def info(self, message, **kwargs):
        self.info_calls.append((message, kwargs))

    def warning(self, message, **kwargs):
        self.warning_calls.append((message, kwargs))

    def error(self, message, **kwargs):
        self.error_calls.append((message, kwargs))


def test_prune_size_validation_logs_event(tmp_path, monkeypatch):
    fake_logger = _FakeLogger()
    monkeypatch.setattr(storage_manager, "logger", fake_logger)

    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    args = _Args(storage_dir=storage_dir, max_mb=0)
    result = prune_size(args)

    assert result == 1
    assert any(
        payload.get("event") == "storage_manager.prune.validation_failed"
        for _, payload in fake_logger.warning_calls
    )


def test_main_logs_command_lifecycle(tmp_path, monkeypatch):
    fake_logger = _FakeLogger()
    monkeypatch.setattr(storage_manager, "logger", fake_logger)

    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        storage_manager,
        "resolve_storage_dir",
        lambda cli_dir, data_root: str(storage_dir),
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "storage_manager",
            "--storage-dir",
            str(storage_dir),
            "stats",
        ],
    )

    result = storage_manager.main()
    assert result == 0

    start_events = [
        payload
        for _, payload in fake_logger.info_calls
        if payload.get("event") == "storage_manager.command_start"
    ]
    end_events = [
        payload
        for _, payload in fake_logger.info_calls
        if payload.get("event") == "storage_manager.command_end"
    ]
    assert len(start_events) == 1
    assert len(end_events) == 1
    assert start_events[0]["command"] == "stats"
    assert end_events[0]["status_code"] == 0
