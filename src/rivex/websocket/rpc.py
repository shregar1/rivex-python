from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from rivex.exceptions.http.exceptions import WebSocketDisconnect


class RPCServer:
    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, method: str, handler: Callable) -> None:
        """Register a callable under ``method`` so it can be invoked by clients.

        The handler will be looked up by name when an ``rpc:request`` with the
        same ``method`` field arrives in :meth:`handle_message`. Handlers may be
        either regular callables or coroutines; the dispatcher awaits the result
        when the handler returns an :class:`Awaitable`.

        Args:
            method: Name clients will use to invoke this handler.
            handler: Callable invoked as ``handler(websocket, params)``. May be
                either sync or async.
        """
        self._handlers[method] = handler

    async def handle_message(self, websocket: Any, message: dict[str, Any]) -> None:
        """Dispatch an inbound message when it is an RPC request.

        Reads ``type``, ``id``, ``method`` and ``params`` from ``message`` and,
        when ``type`` equals ``"rpc:request"``, looks the handler up by name and
        runs it. The result (or any error) is sent back to ``websocket`` as an
        ``rpc:response`` / ``rpc:error`` frame using the request's ``id``. Non-RPC
        messages are silently ignored.

        Args:
            websocket: The WebSocket the message arrived on; used as the first
                positional argument when invoking handlers and as the target of
                the response frames.
            message: Parsed inbound message dict. Only ``type == "rpc:request"``
                messages trigger a handler call.
        """
        msg_type = message.get("type", "")
        if msg_type != "rpc:request":
            return
        req_id = message.get("id")
        method = message.get("method", "")
        params = message.get("params", {})
        handler = self._handlers.get(method)
        if handler is None:
            await self._send_error(websocket, req_id, -32601, f"method not found: {method}")
            return
        try:
            result = (
                await handler(websocket, params)
                if isinstance(handler(websocket, params), Awaitable)
                else handler(websocket, params)
            )
            await self._send_response(websocket, req_id, result)
        except Exception as e:
            await self._send_error(websocket, req_id, -32603, str(e))

    async def _send_response(self, websocket: Any, req_id: str, result: Any) -> None:
        """Serialise and send a successful RPC response frame.

        Builds a ``{"type": "rpc:response", "id": req_id, "result": result}``
        payload, JSON-encodes it, and forwards it to ``websocket``.

        Args:
            websocket: The WebSocket the response should be written to.
            req_id: Identifier copied verbatim from the originating request.
            result: Result value of the handler; serialised by the JSON encoder
                and decoded by the recipient.
        """
        msg = json.dumps({"type": "rpc:response", "id": req_id, "result": result})
        await websocket.send(msg)

    async def _send_error(self, websocket: Any, req_id: str, code: int, message: str) -> None:
        """Serialise and send an ``rpc:error`` frame to ``websocket``.

        Used both when the request references an unknown method and when the
        handler raises an exception during :meth:`handle_message`.

        Args:
            websocket: The WebSocket the error frame should be written to.
            req_id: Identifier copied verbatim from the originating request.
            code: Numeric error code, conventionally aligned with JSON-RPC
                codes (``-32601`` method-not-found, ``-32603`` internal error).
            message: Human-readable description of what went wrong.
        """
        msg = json.dumps({"type": "rpc:error", "id": req_id, "code": code, "message": message})
        await websocket.send(msg)


class RPCClient:
    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout
        self._pending: dict[str, asyncio.Future] = {}
        self._seq = 0

    def _next_id(self) -> str:
        """Generate a fresh RPC request id.

        Combines a monotonic sequence counter with a short random suffix so
        request ids are unique both within a session and across clients.
        Returned ids look like ``"rpc:<n>:<8 hex chars>"``.

        Returns:
            A new request id string that should be paired with the outbound
            ``rpc:request`` frame.
        """
        self._seq += 1
        return f"rpc:{self._seq}:{uuid.uuid4().hex[:8]}"

    async def call(self, send: Callable, receive: Callable, method: str, params: Any = None) -> Any:
        """Invoke a remote RPC method and await its result.

        Builds an ``rpc:request`` frame, ships it via ``send``, and waits on an
        :class:`asyncio.Future` that is resolved by :meth:`handle_response`.
        The wait is bounded by ``self._timeout``; on expiry a ``TimeoutError``
        is raised describing the method that timed out.

        Args:
            send: Awaitable callable that writes a single encoded frame to the
                server. Used to deliver the request payload.
            receive: Unused on this side of the call; accepted for API parity
                with handler-side callables. Responses arrive via
            :meth:`handle_response`.
            method: Name of the remote method to invoke.
            params: Parameters forwarded to the remote handler. Defaults to
                ``None`` when omitted.

        Returns:
            The ``result`` field from the matching ``rpc:response`` frame.

        Raises:
            TimeoutError: When no response arrives within ``self._timeout``.
            WebSocketDisconnect: When the server replied with an error frame
                (raised from :meth:`handle_response`).
        """
        req_id = self._next_id()
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        try:
            msg = json.dumps(
                {"type": "rpc:request", "id": req_id, "method": method, "params": params}
            )
            await send(msg)
            return await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"RPC call {method} timed out after {self._timeout}s") from None
        except Exception:
            self._pending.pop(req_id, None)
            raise

    async def handle_response(self, message: dict[str, Any]) -> None:
        """Resolve the pending future matching an inbound RPC response.

        Pulls ``id`` from ``message`` and matches it against the futures
        registered in :meth:`call`. Success payloads resolve the future with
        their ``result`` field; error payloads raise :class:`WebSocketDisconnect`
        so the caller's ``await`` re-raises with a useful reason. Unknown,
        missing, or already-resolved ids are silently ignored.

        Args:
            message: Parsed inbound message dict. ``id`` selects the future;
                ``error`` / ``code`` + ``message`` indicate failure.
        """
        req_id = message.get("id")
        if not req_id:
            return
        future = self._pending.pop(req_id, None)
        if future is None or future.done():
            return
        if "result" in message:
            future.set_result(message["result"])
        elif "error" in message:
            future.set_exception(
                WebSocketDisconnect(
                    code=1008, reason=message.get("error", {}).get("message", "rpc error")
                )
            )
        elif "code" in message:
            future.set_exception(
                WebSocketDisconnect(code=1008, reason=message.get("message", "rpc error"))
            )


def rpc_method(name: str | None = None) -> Callable:
    """Decorator that tags a function as an RPC method.

    Sets ``_rpc_method`` on the wrapped function so the surrounding RPC
    framework can auto-register handlers by attribute rather than by an
    explicit :meth:`RPCServer.register` call. When ``name`` is omitted, the
    function's ``__name__`` is used.

    Args:
        name: Public method name to expose to clients. Defaults to the
            function's ``__name__``.

    Returns:
        A decorator that records the chosen name on the wrapped function and
        returns the function itself unchanged.
    """
    def decorator(func: Callable) -> Callable:
        """Tag ``func`` with the chosen RPC method name and return it.

        Records ``_rpc_method`` so the surrounding RPC framework can
        auto-register the handler by attribute. The wrapped function is
        returned unchanged so it can still be used as a normal callable.

        Args:
            func: Function being decorated; tagged in place with the
                chosen method name.

        Returns:
            The same ``func``, returned unmodified.
        """
        func._rpc_method = name or func.__name__
        return func

    return decorator
