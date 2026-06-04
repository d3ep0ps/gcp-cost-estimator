# SPDX-License-Identifier: Apache-2.0

import os

import pytest
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from gcp_billing_mcp.http.app import create_app


@pytest.fixture
def http_client(monkeypatch):
    # Mock FastMCP.sse_app to return a dummy Starlette app
    # This isolates testing of the authentication middleware
    mock_inner_app = Starlette(
        routes=[
            Route("/sse", endpoint=lambda _: Response("sse-success", media_type="text/plain")),
            Mount("/messages", app=lambda _: Response("messages-success", media_type="text/plain")),
        ]
    )
    monkeypatch.setattr(FastMCP, "sse_app", lambda _self: mock_inner_app)

    # Set the token environment variable for testing
    os.environ["GCP_BILLING_BEARER_TOKEN"] = "test-secret-token"
    app = create_app()
    client = TestClient(app)
    yield client
    # Clean up
    if "GCP_BILLING_BEARER_TOKEN" in os.environ:
        del os.environ["GCP_BILLING_BEARER_TOKEN"]


def test_unauthorized_if_token_missing(http_client):
    """Assert that requests without an Authorization header are rejected with 401."""
    response = http_client.get("/sse")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"
    assert "missing" in response.json()["message"].lower()


def test_unauthorized_if_token_invalid(http_client):
    """Assert that requests with an invalid token are rejected with 401."""
    headers = {"Authorization": "Bearer wrong-token"}
    response = http_client.get("/sse", headers=headers)
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"
    assert "invalid" in response.json()["message"].lower()


def test_authorized_sse_request_success(http_client):
    """Assert that requests with a valid token via header are accepted."""
    headers = {"Authorization": "Bearer test-secret-token"}
    response = http_client.get("/sse", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("content-type") == "text/plain; charset=utf-8"
    assert response.text == "sse-success"


def test_authorized_sse_query_param_success(http_client):
    """Assert that requests with a valid token via query parameter are accepted."""
    response = http_client.get("/sse?token=test-secret-token")
    assert response.status_code == 200
    assert response.headers.get("content-type") == "text/plain; charset=utf-8"
    assert response.text == "sse-success"
