"""Tests for logging hardening controls.

Covers redaction, truncation, and required failure fields in StructuredLogger.
"""

import json

from gofr_common.logger import StructuredLogger


def _first_json_line(output: str) -> dict:
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        return json.loads(line)
    raise AssertionError("No JSON log line found")


def test_structured_logger_redacts_secret_fields(capsys):
    logger = StructuredLogger(name="test-hardening-redact", json_format=True)

    logger.info(
        "Sensitive payload",
        auth_token="Bearer top-secret-token",
        api_key="super-secret-key",
        password="very-secret",
    )

    captured = capsys.readouterr()
    log_data = _first_json_line(captured.out)

    assert log_data["auth_token"] == "[REDACTED]"
    assert log_data["api_key"] == "[REDACTED]"
    assert log_data["password"] == "[REDACTED]"


def test_structured_logger_truncates_oversized_text(capsys):
    logger = StructuredLogger(name="test-hardening-truncate", json_format=True)

    huge_text = "payload-block " * 300
    logger.info("Large payload", body=huge_text)

    captured = capsys.readouterr()
    log_data = _first_json_line(captured.out)

    assert len(log_data["body"]) < len(huge_text)
    assert log_data["body"].endswith("...[truncated]")


def test_warning_adds_required_failure_fields(capsys):
    logger = StructuredLogger(name="test-hardening-required-fields", json_format=True)

    logger.warning("Warning with missing metadata")

    captured = capsys.readouterr()
    log_data = _first_json_line(captured.out)

    assert log_data["event"]
    assert log_data["operation"]
    assert log_data["stage"]
    assert log_data["dependency"]
    assert log_data["cause_type"]
    assert log_data["remediation"]
