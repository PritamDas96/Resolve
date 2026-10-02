"""Unit tests for :mod:`resolve.logging`.

structlog is configured to print to stdout, so we assert on captured stdout via
pytest's ``capsys`` fixture.
"""

import json

import pytest

from resolve.logging import configure_logging, get_logger


def test_emits_json_with_bound_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", json_logs=True)
    log = get_logger("test-component")

    log.info("hello_event", case_id="C-0001")

    line = capsys.readouterr().out.strip()
    record = json.loads(line)  # output must be valid JSON
    assert record["event"] == "hello_event"
    assert record["case_id"] == "C-0001"
    assert record["logger"] == "test-component"
    assert record["level"] == "info"


def test_level_filtering_drops_debug(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", json_logs=True)
    log = get_logger()

    log.debug("debug_should_be_dropped")

    assert "debug_should_be_dropped" not in capsys.readouterr().out


def test_console_renderer_is_human_readable(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="DEBUG", json_logs=False)
    log = get_logger()

    log.info("console_event")

    out = capsys.readouterr().out
    assert "console_event" in out
