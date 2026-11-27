from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any


class JSONRPCMiddleware:
    """JSON-RPC 2.0 protocol over HTTP POST.

    Exposes registered methods at a single endpoint, accepting
    JSON-RPC 2.0 request objects and returning response objects.

    Usage::

        rpc = JSONRPCMiddleware(endpoint="/api/rpc")

        @rpc.method("add")
        async def add(a: int, b: int) -> int:
            return a + b

        @rpc.method("echo")
        def echo(message: str) -> str:
            return message

        app.add_middleware(rpc)
    """

    def __init__(self, endpoint: str = "/api/rpc", app: Any = None):
        self._endpoint = endpoint
        self._methods: dict[str, Callable] = {}
        self._before_request: list[Callable] = []
        self._after_request: list[Callable] = []

    def method(self, name: str | None = None):
        """Decorator to register a JSON-RPC method.

        Usage::

            @rpc.method("add")
            async def add(a, b): ...
        """
        def decorator(func: Callable) -> Callable:
            """Bind ``func`` as the implementation of the named JSON-RPC method.

            When ``name`` is ``None``, the function's ``__name__`` is
            used as the RPC method name. The function is stored on the
            middleware's method table and returned unchanged so it can
            still be called directly from Python if desired.

            Args:
                func: Callable to register. May be sync or async.

            Returns:
                The same ``func`` instance, for decorator-style use.
            """
            method_name = name or func.__name__
            self._methods[method_name] = func
            return func
        return decorator

    def before_request(self, func: Callable) -> Callable:
        """Register a hook invoked before each RPC handler runs.

        Hooks receive ``(method_name, params)`` and may be sync or
        async. Exceptions raised by a hook are silently swallowed so a
        misbehaving hook cannot break request handling.

        Args:
            func: Callable to invoke before dispatching an RPC. Returned
                unchanged so the call can be used as a decorator.

        Returns:
            The same ``func`` instance, for decorator-style use.
        """
        self._before_request.append(func)
        return func

    def after_request(self, func: Callable) -> Callable:
        """Register a hook invoked after each RPC handler returns.

        Hooks receive ``(method_name, result)`` and may be sync or
        async. Exceptions raised by a hook are silently swallowed so a
        misbehaving hook cannot break request handling.

        Args:
            func: Callable to invoke after dispatching an RPC. Returned
                unchanged so the call can be used as a decorator.

        Returns:
            The same ``func`` instance, for decorator-style use.
        """
        self._after_request.append(func)
        return func

    def _make_error(self, code: int, message: str, id_val: Any = None) -> dict:
        """Build a JSON-RPC 2.0 error object.

        Args:
            code: Numeric JSON-RPC error code (e.g. ``-32601`` for
                method not found).
            message: Human-readable error message.
            id_val: Original request id (or ``None`` for parse errors
                where the id could not be extracted).

        Returns:
            A dict shaped like ``{"jsonrpc": "2.0", "error": {"code":
            ..., "message": ...}, "id": ...}``.
        """
        return {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message},
            "id": id_val,
        }

    def _make_success(self, result: Any, id_val: Any) -> dict:
        """Build a JSON-RPC 2.0 success response.

        Args:
            result: Value returned by the handler. Embedded verbatim
                under ``"result"``.
            id_val: Original request id, echoed back in the response.

        Returns:
            A dict shaped like ``{"jsonrpc": "2.0", "result": ..., "id": ...}``.
        """
        return {"jsonrpc": "2.0", "result": result, "id": id_val}

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Handle a single JSON-RPC 2.0 request envelope.

        Routes matching the configured ``endpoint`` are decoded: GET
        requests are not allowed, POST requests must carry a JSON body
        with the standard ``{jsonrpc, method, params, id}`` shape, and
        batch requests are accepted as JSON arrays. Each entry is
        dispatched to the matching handler (params may be a list or a
        dict) and the corresponding success or error envelope is
        accumulated. Paths that do not match the endpoint are passed
        to ``call_next`` unchanged.

        Args:
            request_data: The in-flight request envelope carried by the
                middleware chain. Reads ``path``, ``method``,
                ``headers`` and ``body``.
            call_next: Awaitable that invokes the next middleware.

        Returns:
            A response dict with ``status`` and ``body`` set to a
            JSON-RPC 2.0 response (single object for a single request,
            array for a batch).
        """
        path = request_data.get("path", "/")
        if path != self._endpoint:
            return await call_next(request_data)

        method = request_data.get("method", "GET").upper()
        if method != "POST":
            return {"status": 405, "body": "Method not allowed"}

        headers = request_data.get("headers", {})
        content_type = ""
        if isinstance(headers, dict):
            content_type = headers.get("content-type", headers.get("Content-Type", ""))

        body = request_data.get("body", "{}")
        if isinstance(body, bytes):
            body = body.decode()

        try:
            request_json = json.loads(body)
        except json.JSONDecodeError:
            return {"status": 400, "body": json.dumps(self._make_error(-32700, "Parse error"))}

        is_batch = isinstance(request_json, list)
        requests = request_json if is_batch else [request_json]
        responses: list[dict | None] = []

        for req in requests:
            if not isinstance(req, dict):
                responses.append(self._make_error(-32600, "Invalid Request", None))
                continue

            req_id = req.get("id")
            if req.get("jsonrpc") != "2.0":
                responses.append(self._make_error(-32600, "Invalid Request", req_id))
                continue

            method_name = req.get("method", "")
            if not method_name:
                responses.append(self._make_error(-32601, "Method not found", req_id))
                continue

            params = req.get("params", [])

            handler = self._methods.get(method_name)
            if handler is None:
                responses.append(self._make_error(-32601, f"Method not found: {method_name}", req_id))
                continue

            for hook in self._before_request:
                try:
                    await hook(method_name, params) if hasattr(hook, "__call__") else hook(method_name, params)
                except Exception:
                    pass

            try:
                if isinstance(params, dict):
                    result = await handler(**params) if hasattr(handler, "__call__") else handler(**params)
                elif isinstance(params, list):
                    result = await handler(*params) if hasattr(handler, "__call__") else handler(*params)
                else:
                    result = await handler(params) if hasattr(handler, "__call__") else handler(params)

                for hook in self._after_request:
                    try:
                        await hook(method_name, result) if hasattr(hook, "__call__") else hook(method_name, result)
                    except Exception:
                        pass

                responses.append(self._make_success(result, req_id))
            except Exception as e:
                responses.append(self._make_error(-32603, str(e), req_id))

        response_body = responses if is_batch else (responses[0] if responses else self._make_error(-32600, "Invalid Request", None))
        return {
            "status": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(response_body),
        }


class XMLRPCMiddleware:
    """XML-RPC protocol over HTTP POST.

    Exposes registered methods at a single endpoint using XML-RPC
    request/response format.

    Usage::

        xmlrpc = XMLRPCMiddleware(endpoint="/api/xmlrpc")

        @xmlrpc.method("add")
        def add(a: int, b: int) -> int:
            return a + b

        app.add_middleware(xmlrpc)
    """

    def __init__(self, endpoint: str = "/api/xmlrpc", app: Any = None):
        self._endpoint = endpoint
        self._methods: dict[str, Callable] = {}

    def method(self, name: str | None = None):
        def decorator(func: Callable) -> Callable:
            """Bind ``func`` as the implementation of the named XML-RPC method.

            When ``name`` is ``None``, the function's ``__name__`` is
            used as the RPC method name. The function is stored on the
            middleware's method table and returned unchanged so it can
            still be called directly from Python if desired.

            Args:
                func: Callable to register. May be sync or async.

            Returns:
                The same ``func`` instance, for decorator-style use.
            """
            method_name = name or func.__name__
            self._methods[method_name] = func
            return func
        return decorator

    def _parse_xmlrpc_request(self, body: bytes) -> tuple[str, list]:
        """Parse the method name and positional parameter list from an XML-RPC body.

        Uses :mod:`xml.etree.ElementTree` to extract the
        ``<methodName>`` and the ordered ``<params>`` block. Each
        ``<value>`` is recursively converted via :meth:`_xml_to_python`
        so the caller receives the arguments in the same form they
        would have been sent as a Python ``list``/``dict``.

        Args:
            body: Raw XML request body bytes.

        Returns:
            A ``(method_name, params)`` tuple where ``method_name`` is
            the string from ``<methodName>`` and ``params`` is the
            list of decoded positional arguments.

        Raises:
            ValueError: When ``<methodName>`` is missing from the body.
            xml.etree.ElementTree.ParseError: When ``body`` is not
                well-formed XML.
        """
        import xml.etree.ElementTree as ET
        root = ET.fromstring(body)
        method_name = root.find("./methodName")
        if method_name is None:
            raise ValueError("Missing methodName")
        params = root.findall("./params/param/value")
        values = []
        for p in params:
            values.append(self._xml_to_python(p))
        return method_name.text or "", values

    def _xml_to_python(self, element) -> Any:
        """Recursively convert an XML-RPC ``<value>`` element to a Python object.

        Recognizes the standard XML-RPC type tags (``<int>``, ``<i4>``,
        ``<double>``, ``<boolean>``, ``<string>``, ``<array>`` and
        ``<struct>``) and falls back to the element's text content for
        anything else. Arrays and structs are processed recursively.

        Args:
            element: An :mod:`xml.etree.ElementTree` element. The
                function inspects the first child tag to determine the
                type.

        Returns:
            The decoded Python value (``int``, ``float``, ``bool``,
            ``str``, ``list`` or ``dict``).
        """
        child = list(element)
        if not child:
            return element.text or ""
        tag = child[0].tag
        text = child[0].text or ""
        if tag == "int" or tag == "i4":
            return int(text)
        elif tag == "double":
            return float(text)
        elif tag == "boolean":
            return text == "1"
        elif tag == "string":
            return text
        elif tag == "array":
            data = child[0].find("data")
            if data is not None:
                return [self._xml_to_python(v) for v in data.findall("value")]
            return []
        elif tag == "struct":
            result = {}
            for member in child[0].findall("member"):
                name = member.find("name")
                value = member.find("value")
                if name is not None and value is not None:
                    result[name.text or ""] = self._xml_to_python(value)
            return result
        return text

    def _python_to_xml(self, value: Any) -> str:
        """Serialize a Python value as an XML-RPC ``<value>`` body fragment.

        Recognizes ``int``, ``float``, ``bool``, ``list``, ``dict`` and
        ``str``; falls back to wrapping the value in ``<string>`` for
        any other type so arbitrary objects still produce a parseable
        response. Recursively serializes container types so nested
        arrays and structs round-trip through XML-RPC.

        Args:
            value: The Python value to encode.

        Returns:
            A string containing the inner XML (without the surrounding
            ``<value>`` tag) ready to be dropped into a ``<param>``.
        """
        if isinstance(value, int):
            return f"<int>{value}</int>"
        elif isinstance(value, float):
            return f"<double>{value}</double>"
        elif isinstance(value, bool):
            return f"<boolean>{'1' if value else '0'}</boolean>"
        elif isinstance(value, list):
            items = "".join(f"<value>{self._python_to_xml(v)}</value>" for v in value)
            return f"<array><data>{items}</data></array>"
        elif isinstance(value, dict):
            members = "".join(
                f"<member><name>{k}</name><value>{self._python_to_xml(v)}</value></member>"
                for k, v in value.items()
            )
            return f"<struct>{members}</struct>"
        else:
            return f"<string>{value}</string>"

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Handle a single XML-RPC request envelope.

        Routes matching the configured ``endpoint`` are decoded: GET
        requests are not allowed, POST requests must carry a
        ``<methodCall>`` body. The method is dispatched positionally
        and the return value is serialized via
        :meth:`_python_to_xml`. Both successful responses and fault
        responses are always returned with HTTP ``200`` and a
        ``text/xml`` body (per the XML-RPC spec), and paths that do
        not match the endpoint are forwarded to ``call_next``
        unchanged.

        Args:
            request_data: The in-flight request envelope. Reads
                ``path``, ``method`` and ``body``.
            call_next: Awaitable that invokes the next middleware.

        Returns:
            A response dict with ``status``, ``headers`` and ``body``
            for XML-RPC requests, or the result of ``call_next`` for
            paths outside the middleware's endpoint.
        """
        path = request_data.get("path", "/")
        if path != self._endpoint:
            return await call_next(request_data)

        method = request_data.get("method", "GET").upper()
        if method != "POST":
            return {"status": 405, "body": "Method not allowed"}

        body = request_data.get("body", b"")
        if isinstance(body, str):
            body = body.encode()

        try:
            method_name, params = self._parse_xmlrpc_request(body)
        except Exception as e:
            fault = f"""<?xml version="1.0"?>
<methodResponse>
  <fault>
    <value><struct>
      <member><name>faultCode</name><value><int>-32600</int></value></member>
      <member><name>faultString</name><value><string>Invalid request: {e}</string></value></member>
    </struct></value>
  </fault>
</methodResponse>"""
            return {"status": 200, "headers": {"Content-Type": "text/xml"}, "body": fault}

        handler = self._methods.get(method_name)
        if handler is None:
            fault = f"""<?xml version="1.0"?>
<methodResponse>
  <fault>
    <value><struct>
      <member><name>faultCode</name><value><int>-32601</int></value></member>
      <member><name>faultString</name><value><string>Method not found: {method_name}</string></value></member>
    </struct></value>
  </fault>
</methodResponse>"""
            return {"status": 200, "headers": {"Content-Type": "text/xml"}, "body": fault}

        try:
            result = await handler(*params) if hasattr(handler, "__call__") else handler(*params)
            xml_result = self._python_to_xml(result)
            body = f"""<?xml version="1.0"?>
<methodResponse>
  <params><param><value>{xml_result}</value></param></params>
</methodResponse>"""
            return {"status": 200, "headers": {"Content-Type": "text/xml"}, "body": body}
        except Exception as e:
            fault = f"""<?xml version="1.0"?>
<methodResponse>
  <fault>
    <value><struct>
      <member><name>faultCode</name><value><int>-32603</int></value></member>
      <member><name>faultString</name><value><string>Internal error: {e}</string></value></member>
    </struct></value>
  </fault>
</methodResponse>"""
            return {"status": 200, "headers": {"Content-Type": "text/xml"}, "body": fault}
