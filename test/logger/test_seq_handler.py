"""Unit tests for SEQ handler reliability counters."""

import logging
import queue
import urllib.error

from gofr_common.logger.seq_handler import SeqHandler


def _record() -> logging.LogRecord:
    return logging.makeLogRecord(
        {
            "name": "test-seq-handler",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "test event",
            "args": (),
        }
    )


def test_emit_queue_full_increments_drop_counter(monkeypatch):
    handler = SeqHandler(server_url="http://seq.example", max_queue_size=1)
    try:
        def _raise_full(_item):
            raise queue.Full()

        monkeypatch.setattr(handler._queue, "put_nowait", _raise_full)

        handler.emit(_record())

        stats = handler.get_stats()
        assert stats["events_dropped_queue_full"] == 1
    finally:
        handler.close()


def test_post_failure_increments_failure_counter_and_records_error(monkeypatch):
    handler = SeqHandler(server_url="http://seq.example")
    try:
        def _raise_url_error(*_args, **_kwargs):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr("urllib.request.urlopen", _raise_url_error)

        handler._post_clef('{"@mt":"test"}')

        stats = handler.get_stats()
        assert stats["post_failures"] == 1
        assert stats["last_post_error"] == "network_error"
    finally:
        handler.close()


def test_post_success_updates_last_success_timestamp(monkeypatch):
    handler = SeqHandler(server_url="http://seq.example")
    try:
        class _OkResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def _ok_urlopen(*_args, **_kwargs):
            return _OkResponse()

        monkeypatch.setattr("urllib.request.urlopen", _ok_urlopen)

        handler._post_clef('{"@mt":"test"}')

        stats = handler.get_stats()
        assert stats["post_failures"] == 0
        assert stats["last_success_utc"] is not None
    finally:
        handler.close()
