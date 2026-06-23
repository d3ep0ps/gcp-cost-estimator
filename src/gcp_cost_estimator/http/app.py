# SPDX-License-Identifier: Apache-2.0

import os
import urllib.parse

from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuthMiddleware:
    """ASGI Middleware enforcing Bearer token authentication."""

    def __init__(self, app: ASGIApp, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Pass non-HTTP protocols through
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract token from header or query string
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("utf-8")

        token_val = None
        if auth_header.startswith("Bearer "):
            token_val = auth_header[len("Bearer ") :].strip()

        if not token_val:
            # Fallback to query parameter (specifically useful for SSE clients)
            query_string = scope.get("query_string", b"").decode("utf-8")
            params = urllib.parse.parse_qs(query_string)
            if "token" in params:
                token_val = params["token"][0]

        if not token_val:
            await self.unauthorized(send, "Missing bearer token")
            return

        if token_val != self.token:
            await self.unauthorized(send, "Invalid bearer token")
            return

        await self.app(scope, receive, send)

    async def unauthorized(self, send: Send, message: str) -> None:
        import json

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        body = json.dumps({"error": "Unauthorized", "message": message}).encode("utf-8")
        await send(
            {
                "type": "http.response.body",
                "body": body,
                "more_body": False,
            }
        )


def create_app() -> ASGIApp:
    """Create the Starlette application with Bearer Authentication wrapping the MCP app."""
    from gcp_cost_estimator.core.logging import configure_logging
    from gcp_cost_estimator.mcp.server import mcp

    # Initialize logging configuration
    configure_logging()

    # Get the raw FastMCP SSE Starlette app
    mcp_sse_app = mcp.sse_app()

    # Retrieve expected token from env — must be set; no insecure default.
    token = os.environ.get("GCP_BILLING_BEARER_TOKEN")
    if not token:
        raise RuntimeError(
            "GCP_BILLING_BEARER_TOKEN must be set before starting the HTTP adapter. "
            "Generate a strong random token and export it as this environment variable."
        )

    # Wrap the app in the authentication middleware
    return BearerAuthMiddleware(mcp_sse_app, token)
