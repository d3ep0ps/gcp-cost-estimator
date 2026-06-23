# SPDX-License-Identifier: Apache-2.0

import socket
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def block_sockets(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Autouse fixture that prevents tests from making network calls.

    Raises RuntimeError if a socket connection is attempted.
    """
    if "integration" in request.keywords:
        return

    original_socket = socket.socket

    def guarded_socket(*args: Any, **kwargs: Any) -> Any:
        family = kwargs.get("family", args[0] if args else socket.AF_INET)
        if family in (socket.AF_INET, socket.AF_INET6):
            msg = "Network/Socket connections are disabled in unit tests to ensure determinism."
            raise RuntimeError(msg)
        return original_socket(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", guarded_socket)


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip integration tests by default unless RUN_INTEGRATION_TESTS=1 is set."""
    if "integration" in item.keywords:
        import os

        if not os.environ.get("RUN_INTEGRATION_TESTS"):
            pytest.skip("Integration tests skipped by default. Set RUN_INTEGRATION_TESTS=1 to run.")


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """Temporary SQLite DB path — cleaned up automatically by pytest even on crash."""
    return str(tmp_path / "test.sqlite")
