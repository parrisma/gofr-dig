"""Housekeeping scenario tests.

Validates that the storage pruning logic correctly removes the oldest
sessions when the total size exceeds the configured limit, and that
the newest sessions survive.

These tests use direct ``FileStorage`` writes (no MCP server) to create
deterministic session data, then invoke ``prune_size`` and check results.
"""

from __future__ import annotations

import time

from gofr_common.storage import FileStorage

from app.management.storage_manager import prune_size


class _PruneArgs:
    """Minimal args object matching what ``prune_size`` expects."""

    def __init__(self, *, max_mb: float, storage_dir: str, group=None):
        self.max_mb = max_mb
        self.storage_dir = storage_dir
        self.data_root = None
        self.group = group
        self.verbose = False
        self.lock_stale_seconds = 3600


def _create_sessions(storage: FileStorage, count: int, size_bytes: int, group: str = "test") -> list[str]:
    """Create ``count`` sessions with deterministic sizing.

    Each session is a blob of ``size_bytes`` random-ish data.  A small
    sleep is inserted between saves so that ``created_at`` timestamps
    differ (prune_size sorts by created_at ascending — oldest first).
    """
    guids: list[str] = []
    for i in range(count):
        # Deterministic payload: repeating byte pattern
        data = bytes([i % 256] * size_bytes)
        guid = storage.save(data, "json", group=group)
        guids.append(guid)
        # Tiny sleep so created_at differs between items
        time.sleep(0.01)
    return guids


class TestHousekeeping:
    """Storage pruning / housekeeping tests."""

    def test_prune_removes_oldest_first(self, tmp_path):
        """When storage exceeds the limit, oldest sessions are deleted."""
        storage_dir = str(tmp_path / "storage")
        storage = FileStorage(storage_dir)

        # Create 5 sessions, each ~1 KB
        guids = _create_sessions(storage, count=5, size_bytes=1024)

        # Total = 5 KB.  Set limit to 3 KB — should delete the 2 oldest.
        args = _PruneArgs(max_mb=3.0 / 1024, storage_dir=storage_dir)
        exit_code = prune_size(args)
        assert exit_code == 0

        remaining = storage.list()
        # The 2 oldest should be gone, 3 newest remain
        assert len(remaining) == 3
        # Oldest guids NOT in remaining
        assert guids[0] not in remaining
        assert guids[1] not in remaining
        # Newest guids still present
        assert guids[2] in remaining
        assert guids[3] in remaining
        assert guids[4] in remaining

    def test_prune_noop_when_under_limit(self, tmp_path):
        """No sessions are deleted when storage is under the limit."""
        storage_dir = str(tmp_path / "storage")
        storage = FileStorage(storage_dir)

        _create_sessions(storage, count=3, size_bytes=512)

        # Total ≈ 1.5 KB, limit = 10 KB — no pruning needed
        args = _PruneArgs(max_mb=10.0 / 1024, storage_dir=storage_dir)
        exit_code = prune_size(args)
        assert exit_code == 0

        remaining = storage.list()
        assert len(remaining) == 3

    def test_prune_empty_storage(self, tmp_path):
        """Pruning an empty storage directory is a no-op."""
        storage_dir = str(tmp_path / "storage")
        FileStorage(storage_dir)  # ensure dir exists

        args = _PruneArgs(max_mb=1.0, storage_dir=storage_dir)
        exit_code = prune_size(args)
        assert exit_code == 0

    def test_prune_deletes_all_when_limit_tiny(self, tmp_path):
        """When the limit is tiny, all items are pruned."""
        storage_dir = str(tmp_path / "storage")
        storage = FileStorage(storage_dir)

        _create_sessions(storage, count=3, size_bytes=1024)

        # Limit = ~0 bytes — everything must go.
        # Note: prune_size may return 1 if it can't reach the target
        # (metadata files contribute to disk usage).
        args = _PruneArgs(max_mb=0.0001, storage_dir=storage_dir)
        prune_size(args)

        remaining = storage.list()
        assert len(remaining) == 0

    def test_prune_with_group_filter(self, tmp_path):
        """Pruning with a group filter only affects that group's sessions."""
        storage_dir = str(tmp_path / "storage")
        storage = FileStorage(storage_dir)

        _create_sessions(storage, count=3, size_bytes=1024, group="group_a")
        group_b_guids = _create_sessions(storage, count=3, size_bytes=1024, group="group_b")

        # Limit = 2 KB on group_a only — should delete 1 oldest from group_a
        args = _PruneArgs(max_mb=2.0 / 1024, storage_dir=storage_dir, group="group_a")
        exit_code = prune_size(args)
        assert exit_code == 0

        remaining = storage.list()
        # group_b should be untouched (3 items)
        for guid in group_b_guids:
            assert guid in remaining

    def test_newest_sessions_survive_pruning(self, tmp_path):
        """After pruning, the most recently created sessions remain."""
        storage_dir = str(tmp_path / "storage")
        storage = FileStorage(storage_dir)

        guids = _create_sessions(storage, count=10, size_bytes=512)

        # Total ≈ 5 KB.  Limit = 2.5 KB — keep ~5 newest.
        args = _PruneArgs(max_mb=2.5 / 1024, storage_dir=storage_dir)
        exit_code = prune_size(args)
        assert exit_code == 0

        remaining = storage.list()
        # The newest 5 (approximately) should survive
        assert len(remaining) >= 4
        assert len(remaining) <= 6
        # The very newest must survive
        assert guids[-1] in remaining
        assert guids[-2] in remaining
