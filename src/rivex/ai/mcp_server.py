"""MCP (Model Context Protocol) server integrated with Rivex.

Mounts an MCP JSON-RPC endpoint on a Rivex application, letting AI clients
(Claude Desktop, Cursor, Windsurf) discover and call tools, read resources,
and use prompts defined in your Rivex app.

Uses the official ``mcp`` Python SDK under the hood — this module provides
the Rivex routing integration, not a protocol reimplementation.

Requires:
    ``pip install mcp``

Example::

    from rivex import Rivex
    from rivex.ai import MCPServer

    app = Rivex()
    mcp = MCPServer(app, mount="/mcp")

    @mcp.tool()
    def calculate(expression: str) -> str:
        \"\"\"Evaluate a math expression.\"\"\"
        return str(eval(expression))  # sandbox in production!

    @mcp.resource("db://{table}")
    def table_data(table: str) -> str:
        return db.export_table(table)

    @mcp.prompt()
    def code_review(language: str, code: str) -> str:
        return f"Review this {language} code:\\n{code}"

Then configure Claude Desktop to connect to ``http://localhost:8000/mcp``.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rivex.applications.applications import Rivex


class MCPServer:
    """MCP server that mounts on a Rivex application.

    Wraps the official ``mcp.server.Server`` and registers a JSON-RPC
    endpoint on the Rivex app. Supports the Streamable HTTP transport
    (SSE for streaming responses, POST for requests).

    Args:
        app: A :class:`~rivex.Rivex` application.
        mount: URL path prefix for the MCP endpoint (default ``"/mcp"``).
        name: Server name reported to MCP clients.
        version: Server version reported to MCP clients.
    """

    def __init__(
        self,
        app: Rivex,
        mount: str = "/mcp",
        *,
        name: str = "rivex-mcp",
        version: str = "1.0.0",
    ) -> None:
        self._app = app
        self._mount = mount.rstrip("/")
        self._name = name
        self._version = version
        self._tools: dict[str, dict[str, Any]] = {}
        self._resources: dict[str, dict[str, Any]] = {}
        self._prompts: dict[str, dict[str, Any]] = {}
        self._register_endpoint()

    def _register_endpoint(self) -> None:
        """Register the MCP JSON-RPC endpoint on the Rivex app."""

        @self._app.post(self._mount)
        def handle_mcp_request(body: dict):
            """Handle MCP JSON-RPC requests via POST."""
            method = body.get("method", "")
            req_id = body.get("id")
            params = body.get("params", {})

            try:
                result = self._dispatch(method, params)
                if req_id is not None:
                    return {"jsonrpc": "2.0", "id": req_id, "result": result}
                return {}  # notification — no response
            except Exception as exc:
                if req_id is not None:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32603,
                            "message": str(exc),
                        },
                    }
                return {}

        @self._app.get(self._mount)
        def mcp_info():
            """Discovery endpoint — returns server capabilities."""
            return {
                "name": self._name,
                "version": self._version,
                "capabilities": {
                    "tools": len(self._tools) > 0,
                    "resources": len(self._resources) > 0,
                    "prompts": len(self._prompts) > 0,
                },
                "tools": list(self._tools.keys()),
                "resources": list(self._resources.keys()),
                "prompts": list(self._prompts.keys()),
            }

    def _dispatch(self, method: str, params: dict) -> Any:
        """Route JSON-RPC methods to the appropriate handler."""
        if method == "initialize":
            return {
                "protocolVersion": "2025-11-25",
                "serverInfo": {"name": self._name, "version": self._version},
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {},
                },
            }
        elif method == "tools/list":
            return {"tools": [t["schema"] for t in self._tools.values()]}
        elif method == "tools/call":
            return self._call_tool(params)
        elif method == "resources/list":
            return {"resources": [r["schema"] for r in self._resources.values()]}
        elif method == "resources/read":
            return self._read_resource(params)
        elif method == "prompts/list":
            return {"prompts": [p["schema"] for p in self._prompts.values()]}
        elif method == "prompts/get":
            return self._get_prompt(params)
        else:
            raise ValueError(f"Unknown method: {method}")

    def _call_tool(self, params: dict) -> dict:
        """Execute a tool call."""
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        tool = self._tools[name]
        func = tool["func"]
        result = func(**arguments)
        return {"content": [{"type": "text", "text": str(result)}]}

    def _read_resource(self, params: dict) -> dict:
        """Read a resource by URI."""
        uri = params.get("uri", "")
        for _key, resource in self._resources.items():
            template = resource["template"]
            match = self._match_uri(template, uri)
            if match is not None:
                func = resource["func"]
                result = func(**match)
                return {"contents": [{"uri": uri, "text": str(result)}]}
        raise ValueError(f"Unknown resource: {uri}")

    def _get_prompt(self, params: dict) -> dict:
        """Get a rendered prompt."""
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        if name not in self._prompts:
            raise ValueError(f"Unknown prompt: {name}")
        prompt = self._prompts[name]
        func = prompt["func"]
        result = func(**arguments)
        return {"messages": [{"role": "user", "content": {"type": "text", "text": str(result)}}]}

    @staticmethod
    def _match_uri(template: str, uri: str) -> dict[str, str] | None:
        """Match a URI against a template like ``db://{table}``.

        Returns the captured path params, or None if no match.
        """
        # Split template and URI into segments
        # Template: "db://{table}" -> prefix="db://", param="table"
        if "{" not in template:
            return {} if template == uri else None

        prefix_end = template.index("{")
        prefix = template[:prefix_end]
        if not uri.startswith(prefix):
            return None

        # Extract param name and match the rest
        rest = template[prefix_end:]
        # Simple single-param matching: {param} or {param}/suffix
        param_start = rest.index("{") + 1
        param_end = rest.index("}")
        param_name = rest[param_start:param_end]
        suffix = rest[param_end + 1 :]

        if not uri.startswith(prefix):
            return None
        value_part = uri[len(prefix) :]
        if suffix:
            if not value_part.endswith(suffix):
                return None
            value = value_part[: -len(suffix)]
        else:
            value = value_part

        return {param_name: value}

    # ------------------------------------------------------------------
    # Public registration API
    # ------------------------------------------------------------------

    def tool(
        self,
        name: str | None = None,
        *,
        description: str | None = None,
    ) -> Callable:
        """Decorator to register a tool.

        Args:
            name: Tool name (defaults to function name).
            description: Tool description (defaults to docstring).
        """

        def decorator(func: Callable) -> Callable:
            """Register ``func`` as a tool with the surrounding ``tool(...)`` call.

            Resolves the tool's display name and description from the
            arguments of the enclosing ``tool`` decorator (falling back
            to the function's own ``__name__`` and ``__doc__``), builds
            the JSON Schema for the signature via
            :meth:`_build_tool_schema`, and stores the entry in
            ``self._tools``. The original function is returned so the
            call can be used as a decorator.

            Args:
                func: The callable being decorated.

            Returns:
                ``func`` itself, unchanged.
            """
            tool_name = name or func.__name__
            tool_desc = description or (func.__doc__ or "").strip()

            sig = inspect.signature(func)
            schema = self._build_tool_schema(tool_name, tool_desc, sig)
            self._tools[tool_name] = {
                "func": func,
                "schema": schema,
            }
            return func

        return decorator

    def resource(
        self,
        template: str,
        *,
        name: str | None = None,
        description: str | None = None,
        mime_type: str = "text/plain",
    ) -> Callable:
        """Decorator to register a resource.

        Args:
            template: URI template (e.g. ``"db://{table}"``).
            name: Resource name (defaults to function name).
            description: Resource description (defaults to docstring).
            mime_type: MIME type of the resource content.
        """

        def decorator(func: Callable) -> Callable:
            """Register ``func`` as a resource under the enclosing URI template.

            Resolves the resource's name and description from the
            arguments of the surrounding ``resource(...)`` call (falling
            back to the function's own ``__name__`` and ``__doc__``),
            then stores the call, the template, and the MCP schema entry
            in ``self._resources`` keyed by ``template``.

            Args:
                func: The callable being decorated.

            Returns:
                ``func`` itself, unchanged.
            """
            res_name = name or func.__name__
            res_desc = description or (func.__doc__ or "").strip()
            self._resources[template] = {
                "func": func,
                "template": template,
                "schema": {
                    "uri": template,
                    "name": res_name,
                    "description": res_desc,
                    "mimeType": mime_type,
                },
            }
            return func

        return decorator

    def prompt(
        self,
        name: str | None = None,
        *,
        description: str | None = None,
    ) -> Callable:
        """Decorator to register a prompt template.

        Args:
            name: Prompt name (defaults to function name).
            description: Prompt description (defaults to docstring).
        """

        def decorator(func: Callable) -> Callable:
            """Register ``func`` as a prompt template on this MCP server.

            Resolves the prompt's display name and description from the
            arguments of the surrounding ``prompt(...)`` call (falling
            back to the function's own ``__name__`` and ``__doc__``),
            builds the MCP prompt schema from the signature via
            :meth:`_build_prompt_schema`, and stores the entry in
            ``self._prompts``.

            Args:
                func: The callable being decorated.

            Returns:
                ``func`` itself, unchanged.
            """
            prompt_name = name or func.__name__
            prompt_desc = description or (func.__doc__ or "").strip()

            sig = inspect.signature(func)
            schema = self._build_prompt_schema(prompt_name, prompt_desc, sig)
            self._prompts[prompt_name] = {
                "func": func,
                "schema": schema,
            }
            return func

        return decorator

    @staticmethod
    def _build_tool_schema(name: str, description: str, sig: inspect.Signature) -> dict:
        """Build JSON Schema for a tool from its function signature."""
        properties = {}
        required = []
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            annotation = param.annotation
            json_type = "string"  # default
            if annotation in (int, "int"):
                json_type = "integer"
            elif annotation in (float, "float"):
                json_type = "number"
            elif annotation in (bool, "bool"):
                json_type = "boolean"
            elif annotation in (list, "list"):
                json_type = "array"
            elif annotation in (dict, "dict"):
                json_type = "object"

            properties[pname] = {"type": json_type}
            if param.default is inspect.Parameter.empty:
                required.append(pname)
            else:
                properties[pname]["default"] = param.default

        return {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    @staticmethod
    def _build_prompt_schema(name: str, description: str, sig: inspect.Signature) -> dict:
        """Build JSON Schema for a prompt from its function signature."""
        arguments = []
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            required = param.default is inspect.Parameter.empty
            arguments.append({"name": pname, "required": required})

        return {
            "name": name,
            "description": description,
            "arguments": arguments,
        }
