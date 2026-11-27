"""Serverless adapters for AWS Lambda, Cloudflare Workers, Vercel Edge, and Azure Functions.

Usage::

    from rivex import Rivex
    from rivex.native.serverless import AwsLambdaHandler, CloudflareHandler, VercelHandler, AzureFunctionHandler

    app = Rivex()

    # AWS Lambda (via API Gateway / ALB / Lambda URL)
    handler = AwsLambdaHandler(app)

    # Cloudflare Workers
    worker = CloudflareHandler(app)

    # Vercel Edge / Serverless Functions
    vercel_handler = VercelHandler(app)

    # Azure Functions
    azure_handler = AzureFunctionHandler(app)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


class ServerlessAdapter:
    """Base class for serverless adapters."""

    def __init__(self, app: Any):
        from rivex.native.asgi import ASGIAdapter

        self.app = app
        self.asgi = ASGIAdapter(app)

    def _asgi_scope(
        self,
        method: str,
        path: str,
        headers: list[tuple[bytes, bytes]],
        body: bytes,
        query_string: str = "",
        scheme: str = "https",
        server: tuple[str, int] | None = None,
        client: tuple[str, int] | None = None,
    ) -> dict[str, Any]:
        """Build an ASGI ``http`` scope from a serverless invocation's inputs.

        Constructs the minimal scope dict required by the ASGI adapter from
        the per-request pieces that serverless runtimes provide: HTTP method,
        path, headers, body, query string, scheme, and the ``server`` /
        ``client`` tuples. Defaults are applied for ``server`` and ``client``
        so callers in serverless runtimes — which typically do not expose
        those — can omit them.

        Args:
            method: HTTP method string (any case). Normalised to upper case.
            path: URL path component of the incoming request, without the
                query string.
            headers: Already-encoded ``(name_bytes, value_bytes)`` header
                pairs in ASGI order.
            body: Raw request body bytes; included for parity with the
                adapter interface but not embedded in the scope itself.
            query_string: Raw query string (without leading ``?``). Empty
                when the request has no query.
            scheme: URL scheme, typically ``"https"`` for serverless edges
                and ``"http"`` for local development.
            server: ``(host, port)`` tuple identifying the server. Defaults
                to ``("localhost", 443)``.
            client: ``(host, port)`` tuple identifying the calling client.
                Defaults to ``("127.0.0.1", 0)``.

        Returns:
            A dict shaped like a standard ASGI ``http`` scope, ready to be
            passed to the adapter's ``__call__`` alongside the receive/send
            callables.
        """
        return {
            "type": "http",
            "http_version": "1.1",
            "method": method.upper(),
            "path": path,
            "raw_path": path.encode(),
            "headers": headers,
            "query_string": query_string.encode(),
            "scheme": scheme,
            "server": server or ("localhost", 443),
            "client": client or ("127.0.0.1", 0),
        }

    async def _run_asgi(
        self, scope: dict[str, Any], body: bytes
    ) -> dict[str, Any]:
        """Run the ASGI app and return the raw response dict."""
        received = False
        response_holder: dict[str, Any] = {}

        async def receive() -> dict[str, Any]:
            """ASGI ``receive`` callable that yields the request body once.

            Returns the captured request body on the first invocation as a
            standard ``http.request`` ASGI message with ``more_body=False``;
            subsequent invocations yield an ``http.disconnect`` so the
            application can cleanly finish its handling.
            """
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            """ASGI ``send`` callable that aggregates the response into ``response_holder``.

            Captures the status code and headers from the first
            ``http.response.start`` message, then concatenates the bytes
            from any ``http.response.body`` message into ``response_holder``
            so the caller can return a single ``{status, headers, body}``
            dict to the serverless runtime.
            """
            if message["type"] == "http.response.start":
                response_holder["status"] = message["status"]
                response_holder["headers"] = message.get("headers", [])
            elif message["type"] == "http.response.body":
                existing = response_holder.get("body", b"")
                response_holder["body"] = existing + message.get("body", b"")

        asgi_app = self.asgi.__call__(scope, receive, send)
        await asgi_app
        return {
            "status": response_holder.get("status", 500),
            "headers": response_holder.get("headers", []),
            "body": response_holder.get("body", b""),
        }


class AwsLambdaHandler(ServerlessAdapter):
    """Adapter for AWS Lambda behind API Gateway REST/HTTP, ALB, or Lambda Function URL.

    Your ``lambda_handler`` entry point::

        handler = AwsLambdaHandler(app)

        def lambda_handler(event, context):
            return handler(event, context)
    """

    def __call__(self, event: dict, context: Any = None) -> dict:
        version = event.get("version", "1.0")
        headers_raw: list[tuple[bytes, bytes]] = [
            (k.lower().encode(), str(v).encode()) for k, v in event.get("headers", {}).items()
        ]

        method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get(
            "method", "GET"
        )

        if version == "2.0":
            path = event.get("rawPath", "/")
            qs = event.get("rawQueryString", "")
            body_b64 = event.get("body") or ""
            is_b64 = event.get("isBase64Encoded", False)
            if "cookies" in event:
                for c in event["cookies"]:
                    headers_raw.append((b"cookie", c.encode()))
        else:
            path = event.get("path", "/")
            qs_raw = event.get("multiValueQueryStringParameters", {}) or {}
            qs = "&".join(
                f"{k}={v[0] if isinstance(v, list) else v}"
                for k, values in qs_raw.items()
                for v in (values if isinstance(values, list) else [values])
            )
            body_b64 = event.get("body") or ""
            is_b64 = event.get("isBase64Encoded", False)

        import base64

        body = base64.b64decode(body_b64) if is_b64 else body_b64.encode()

        scope = self._asgi_scope(method, path, headers_raw, body, qs, client=("127.0.0.1", 0))

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            raw = loop.run_until_complete(self._run_asgi(scope, body))
        finally:
            loop.close()

        resp_body = raw.get("body", b"")
        if isinstance(resp_body, str):
            resp_body = resp_body.encode()

        response_headers = {}
        multi_value_headers: dict[str, list[str]] = {}
        for k, v in raw.get("headers", []):
            if isinstance(k, bytes):
                k = k.decode()
            if isinstance(v, bytes):
                v = v.decode()
            if k.lower() == "set-cookie":
                multi_value_headers.setdefault("set-cookie", []).append(v)
            else:
                response_headers[k] = v

        return {
            "statusCode": raw.get("status", 200),
            "headers": response_headers,
            "multiValueHeaders": multi_value_headers,
            "body": base64.b64encode(resp_body).decode(),
            "isBase64Encoded": True,
        }


class CloudflareHandler(ServerlessAdapter):
    """Adapter for Cloudflare Workers.

    Export as the default fetch handler::

        handler = CloudflareHandler(app)

        async def fetch(request, env, ctx):
            return await handler(request, env, ctx)
    """

    async def __call__(self, request: Any, env: Any = None, ctx: Any = None) -> Any:
        method = request.method
        path = request.url.path
        qs = request.url.query
        body = await request.body() if hasattr(request, "body") else b""
        headers_raw: list[tuple[bytes, bytes]] = []
        if hasattr(request, "headers"):
            for k, v in request.headers.items():
                headers_raw.append((k.lower().encode(), v.encode()))

        scope = self._asgi_scope(method, path, headers_raw, body, qs)
        raw = await self._run_asgi(scope, body)

        resp_headers = {
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in raw.get("headers", [])
        }

        return {
            "statusCode": raw.get("status", 200),
            "headers": resp_headers,
            "body": raw.get("body", b"").decode() if isinstance(raw.get("body"), bytes) else raw.get("body", ""),
        }


class VercelHandler(ServerlessAdapter):
    """Adapter for Vercel Serverless / Edge Functions.

    Export as::

        handler = VercelHandler(app)

        async def vercel_handler(request):
            return await handler(request)
    """

    async def __call__(self, request: Any) -> Any:
        method = request.method
        path = request.url.path if hasattr(request, "url") else "/"
        qs = request.url.query if hasattr(request, "url") and hasattr(request.url, "query") else ""
        body = await request.body() if hasattr(request, "body") else b""

        headers_raw: list[tuple[bytes, bytes]] = []
        if hasattr(request, "headers"):
            for k, v in request.headers.items():
                headers_raw.append((k.lower().encode(), v.encode() if isinstance(v, str) else v))

        scope = self._asgi_scope(method, path, headers_raw, body, qs)
        raw = await self._run_asgi(scope, body)

        from rivex.http.responses import Response

        resp = Response(
            content=raw.get("body", b""),
            status_code=raw.get("status", 200),
            headers={
                k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                for k, v in raw.get("headers", [])
            },
        )
        return resp


class AzureFunctionHandler(ServerlessAdapter):
    """Adapter for Azure Functions (HTTP trigger).

    Your ``__init__.py`` entry point::

        handler = AzureFunctionHandler(app)

        async def main(req):
            return await handler(req)
    """

    async def __call__(self, req: Any) -> Any:
        method = req.method if hasattr(req, "method") else "GET"
        path = req.url.path if hasattr(req, "url") and hasattr(req.url, "path") else "/"
        qs = req.url.query if hasattr(req, "url") and hasattr(req.url, "query") else ""

        body = req.get_body() if hasattr(req, "get_body") else b""
        if hasattr(body, "__await__"):
            body = await body

        headers_raw: list[tuple[bytes, bytes]] = []
        if hasattr(req, "headers"):
            for k, v in req.headers.items():
                headers_raw.append((k.lower().encode(), v.encode() if isinstance(v, str) else v))

        scope = self._asgi_scope(method, path, headers_raw, body, qs)
        raw = await self._run_asgi(scope, body)

        resp_headers = {
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in raw.get("headers", [])
        }

        return {
            "statusCode": raw.get("status", 200),
            "headers": resp_headers,
            "body": raw.get("body", b""),
        }
