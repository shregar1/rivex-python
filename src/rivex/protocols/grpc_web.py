from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any


class GRPCWebMiddleware:
    """Bridges gRPC-Web requests from browsers to gRPC services.

    gRPC-Web allows browser-based clients to call gRPC services
    using HTTP/1.1 or HTTP/2, translating between the gRPC-Web
    protocol (text/grpc-web or application/grpc-web-text) and
    native gRPC calls.

    Usage::

        app.add_middleware(GRPCWebMiddleware, grpc_server=my_grpc_server)

    Works with any gRPC service registered on the ``GRPCServer``.
    """

    def __init__(
        self,
        grpc_server: Any = None,
        app: Any = None,
        base_path: str = "/grpc",
    ):
        self._grpc_server = grpc_server
        self._base_path = base_path
        self._service_handlers: dict[str, Callable] = {}

    def add_service(self, service_name: str, handler: Callable) -> None:
        """Register a synchronous or async handler for a gRPC service.

        The handler is invoked whenever a request targeting ``service_name``
        arrives via ``process``. It receives ``(service_name, method_name,
        raw_body)`` and must return the serialized response body (as
        ``bytes`` or a JSON-serializable dict).

        Args:
            service_name: Dotted service name, e.g. ``helloworld.Greeter``.
            handler: Callable invoked for each method of ``service_name``.
        """
        self._service_handlers[service_name] = handler

    def _parse_grpc_request(self, body: bytes, content_type: str) -> tuple[str, bytes]:
        """Decode the framing applied to a gRPC-Web request body.

        When the body was carried as ``application/grpc-web-text`` it is
        base64-decoded; otherwise it is forwarded verbatim. Returns the
        decoded body. Failures raised during decoding are not caught
        here — ``process`` is responsible for translating them to an HTTP
        ``400`` response.

        Args:
            body: Raw request body bytes (or already-decoded bytes for
                the binary ``grpc-web`` framing).
            content_type: The ``Content-Type`` header from the request.

        Returns:
            The decoded body ready to be handed to the underlying gRPC
            stub as a serialized protobuf.
        """
        if "grpc-web-text" in content_type:
            body = base64.b64decode(body.decode())
        return body

    def _encode_grpc_response(self, data: bytes, compressed: bool = False) -> bytes:
        """Wrap a response payload in a gRPC-Web frame.

        Frames the payload with the standard 1-byte ``compressed`` flag
        and a 4-byte big-endian length prefix.

        Args:
            data: The serialized response bytes.
            compressed: When true, set the flag bit to ``1`` so the
                client knows the payload is compressed.

        Returns:
            The framed payload as ``bytes``.
        """
        frame = bytearray()
        frame.append(1 if compressed else 0)
        frame.extend(len(data).to_bytes(4, "big"))
        frame.extend(data)
        return bytes(frame)

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Translate a gRPC-Web request into a gRPC call and frame the response.

        Requests whose path does not start with ``self._base_path`` are
        forwarded to ``call_next`` unchanged. Otherwise this middleware
        enforces the gRPC-Web content types, parses the service/method
        from the path, dispatches to either a locally registered handler
        or the bound ``GRPCServer`` via ``_call_grpc``, and finally frames
        the reply with ``_encode_grpc_response`` (and base64-encodes it
        when ``grpc-web-text`` was used). Errors during framing or
        handler dispatch are reported with the appropriate HTTP status.

        Args:
            request_data: The in-flight request envelope carried by the
                middleware chain.
            call_next: Awaitable that invokes the next middleware/handler.

        Returns:
            A response dict with ``status``, ``headers`` and ``body`` for
            gRPC-Web requests, or the result of ``call_next`` for paths
            outside this middleware's base path.
        """
        path = request_data.get("path", "/")
        if not path.startswith(self._base_path):
            return await call_next(request_data)

        method = request_data.get("method", "POST").upper()
        if method != "POST":
            return {"status": 405, "body": "Method not allowed"}

        headers = request_data.get("headers", {})
        if isinstance(headers, dict):
            content_type = headers.get("content-type", headers.get("Content-Type", ""))
            te = headers.get("te", headers.get("TE", ""))
        else:
            content_type = ""
            te = ""

        if "grpc-web" not in content_type and "grpc-web-text" not in content_type:
            return {"status": 415, "body": "Content-Type must be application/grpc-web or application/grpc-web-text"}

        body = request_data.get("body", b"")
        if isinstance(body, str):
            body = body.encode()

        try:
            raw = self._parse_grpc_request(body, content_type)
        except Exception:
            return {"status": 400, "body": "Invalid gRPC-Web request framing"}

        service_method = path[len(self._base_path):].lstrip("/")
        service_parts = service_method.split("/")
        if len(service_parts) != 2:
            return {"status": 400, "body": "Path must be /grpc/{service}/{method}"}

        service_name, method_name = service_parts
        handler = self._service_handlers.get(service_name)
        if handler is None:
            if self._grpc_server:
                grpc_response = await self._call_grpc(service_name, method_name, raw)
            else:
                return {"status": 501, "body": f"No handler for service '{service_name}'"}
        else:
            try:
                grpc_response = await handler(service_name, method_name, raw)
            except Exception as e:
                return {"status": 500, "body": f"Handler error: {e}"}

        if isinstance(grpc_response, dict):
            grpc_response = json.dumps(grpc_response).encode()

        encoded = self._encode_grpc_response(grpc_response)
        should_base64 = "grpc-web-text" in content_type
        if should_base64:
            encoded = base64.b64encode(encoded)

        response_headers = {
            "Content-Type": content_type,
            "grpc-encoding": "identity",
            "grpc-accept-encoding": "gzip",
        }

        return {
            "status": 200,
            "headers": response_headers,
            "body": encoded,
        }

    async def _call_grpc(self, service_name: str, method_name: str, request_body: bytes) -> bytes:
        """Dispatch a single gRPC-Web request through the underlying gRPC server.

        Resolves the gRPC target from ``self._grpc_server``, opens a
        ``GRPCClient``, locates the matching stub class and request
        protobuf class via the lookup helpers, parses the incoming body,
        awaits ``client.call``, and serializes the response back to bytes.

        Args:
            service_name: Dotted service name as carried in the URL.
            method_name: Name of the RPC method on the stub.
            request_body: Already-decoded raw protobuf body bytes.

        Returns:
            The serialized response protobuf, ready to be framed by
            ``_encode_grpc_response``.

        Raises:
            RuntimeError: When no gRPC server was configured on the
                middleware.
            ImportError: When the optional ``grpcio`` library is missing.
            ValueError: When no stub or request class can be located.
        """
        if self._grpc_server is None:
            raise RuntimeError("No gRPC server configured")

        try:
            import grpc
        except ImportError:
            raise ImportError("grpcio library required")

        from rivex.protocols.grpc import GRPCClient

        target = getattr(self._grpc_server, "_host", "localhost") + ":" + str(
            getattr(self._grpc_server, "_port", 50051)
        )
        client = GRPCClient(target=target)

        service_class = self._find_stub_class(service_name)
        if service_class is None:
            raise ValueError(f"No stub class found for service '{service_name}'")

        request_class = self._find_request_class(service_class, method_name)
        if request_class is None:
            raise ValueError(f"No request class for {service_name}.{method_name}")

        request = request_class.FromString(request_body)
        response = await client.call(service_class, method_name, request)
        return response.SerializeToString()

    def _find_stub_class(self, service_name: str) -> type | None:
        """Locate the ``<Service>Stub`` class in any loaded module.

        Walks every entry in ``sys.modules`` looking for an attribute named
        ``"<service_name>Stub"``. The first match wins. Returns ``None`` if
        no module has exposed such an attribute.

        Args:
            service_name: Dotted service name, e.g. ``helloworld.Greeter``.

        Returns:
            The stub class if found, otherwise ``None``.
        """
        try:
            import sys as _sys
            for mod_name in list(_sys.modules.keys()):
                mod = _sys.modules[mod_name]
                stub_name = f"{service_name}Stub"
                if hasattr(mod, stub_name):
                    return getattr(mod, stub_name)
            return None
        except Exception:
            return None

    def _find_request_class(self, stub_class: type, method_name: str) -> type | None:
        """Infer the request protobuf class for a given stub method.

        Inspects every method on ``stub_class`` whose name matches
        ``method_name`` and returns the type annotation of its first
        positional parameter. This is a best-effort lookup that relies
        on the generated stubs exposing PEP 604-style annotations.

        Args:
            stub_class: The stub class returned by ``_find_stub_class``.
            method_name: Name of the RPC method to introspect.

        Returns:
            The request protobuf class, or ``None`` when no matching
            method or annotation can be discovered.
        """
        try:
            import inspect
            for _, method in inspect.getmembers(stub_class, inspect.isfunction):
                if method.__name__ == method_name:
                    hints = inspect.get_annotations(method)
                    params = list(hints.keys())
                    if params:
                        return hints[params[0]]
            return None
        except Exception:
            return None


class GRPCWebServer:
    """Standalone gRPC-Web server that translates HTTP/1.1 to gRPC.

    Usage::

        server = GRPCWebServer(grpc_target="localhost:50051")
        server.add_service("helloworld.Greeter", GreeterStub)
        server.start()
    """

    def __init__(self, grpc_target: str = "localhost:50051", port: int = 8080):
        self._grpc_target = grpc_target
        self._port = port
        self._services: dict[str, type] = {}

    def add_service(self, service_name: str, stub_class: type) -> None:
        """Register a generated gRPC stub class against this server.

        Args:
            service_name: Dotted service name used in incoming URLs.
            stub_class: The generated ``<Service>Stub`` class.
        """
        self._services[service_name] = stub_class
