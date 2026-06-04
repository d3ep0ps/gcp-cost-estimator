import logging
import sys
from pathlib import Path

import pytest

from gcp_billing_mcp.core.logging import configure_logging


@pytest.fixture(autouse=True)
def reset_logger() -> None:
    """Ensure the logger is clean before and after each test."""
    logger = logging.getLogger("gcp_billing_mcp")
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    yield
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    logger.propagate = True


def test_configure_logging_defaults(monkeypatch, tmp_path) -> None:
    """Verifies default logging config: INFO level, stderr handler, default file handler."""
    # Mock home directory to avoid writing to user's real home directory
    fake_home = tmp_path / "fake_home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # Ensure environment variables are clear
    monkeypatch.delenv("GCP_BILLING_LOG_LEVEL", raising=False)
    monkeypatch.delenv("GCP_BILLING_LOG_FILE", raising=False)

    configure_logging()

    logger = logging.getLogger("gcp_billing_mcp")
    assert logger.level == logging.INFO
    assert not logger.propagate

    # Assert handlers
    handlers = logger.handlers
    assert len(handlers) == 2

    # Check stderr stream handler
    stream_handlers = [
        h
        for h in handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]
    assert len(stream_handlers) == 1
    assert stream_handlers[0].stream == sys.stderr

    # Check default file handler
    file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    expected_path = fake_home / ".gcp-billing-mcp" / "mcp.log"
    assert Path(file_handlers[0].baseFilename) == expected_path.resolve()
    assert expected_path.exists()


def test_configure_logging_custom_level(monkeypatch) -> None:
    """Verifies that GCP_BILLING_LOG_LEVEL environment variable is respected."""
    monkeypatch.setenv("GCP_BILLING_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("GCP_BILLING_LOG_FILE", "none")  # disable file logging

    configure_logging()

    logger = logging.getLogger("gcp_billing_mcp")
    assert logger.level == logging.DEBUG


def test_configure_logging_custom_file(monkeypatch, tmp_path) -> None:
    """Verifies that GCP_BILLING_LOG_FILE environment variable configures the file handler path."""
    monkeypatch.delenv("GCP_BILLING_LOG_LEVEL", raising=False)

    custom_log_file = tmp_path / "subdir" / "custom.log"
    monkeypatch.setenv("GCP_BILLING_LOG_FILE", str(custom_log_file))

    configure_logging()

    logger = logging.getLogger("gcp_billing_mcp")
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert Path(file_handlers[0].baseFilename) == custom_log_file.resolve()
    assert custom_log_file.exists()


def test_configure_logging_file_disabled(monkeypatch) -> None:
    """Verifies that GCP_BILLING_LOG_FILE=none disables the file logging handler."""
    monkeypatch.setenv("GCP_BILLING_LOG_FILE", "none")

    configure_logging()

    logger = logging.getLogger("gcp_billing_mcp")
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 0


def test_configure_logging_file_error(monkeypatch, capsys) -> None:
    """Verifies that failures during FileHandler setup write a warning to stderr."""
    # Write to a path that should throw permission/directory issues
    monkeypatch.setenv("GCP_BILLING_LOG_FILE", "/nonexistent_root_dir_abc/log.log")

    configure_logging()

    captured = capsys.readouterr()
    assert "Warning: Failed to setup file logging" in captured.err
