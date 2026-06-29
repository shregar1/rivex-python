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
            method_name = name or func.__name__
            self._methods[method_name] = func
            return func
        return decorator

    def before_request(self, func: Callable) -> Callable:
        self._before_request.append(func)
        return func

    def after_request(self, func: Callable) -> Callable:
        self._after_request.append(func)
        return func

    def _make_error(self, code: int, message: str, id_val: Any = None) -> dict:
        return {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message},
            "id": id_val,
        }

    def _make_success(self, result: Any, id_val: Any) -> dict:
        return {"jsonrpc": "2.0", "result": result, "id": id_val}

    async def process(self, request_data: dict, call_next: Callable) -> dict:
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
            method_name = name or func.__name__
            self._methods[method_name] = func
            return func
        return decorator

    def _parse_xmlrpc_request(self, body: bytes) -> tuple[str, list]:
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
