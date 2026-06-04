# SPDX-License-Identifier: Apache-2.0

import socket
import sys

import pytest

import gcp_billing_mcp


def test_package_imports() -> None:
    """Verify that importing the package works and version is correct."""
    assert gcp_billing_mcp.__version__ == "0.1.0"


def test_python_version_supported() -> None:
    """Verify that python version is at least 3.13."""
    assert sys.version_info >= (3, 13)


def test_network_is_blocked_in_tests() -> None:
    """Verify that attempting to create a socket raises RuntimeError due to block_sockets."""
    with pytest.raises(RuntimeError, match="Network/Socket connections are disabled"):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
