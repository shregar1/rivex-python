"""
JSON-RPC over WebRTC data channels.

Provides:
- ``DataChannelRPC`` — request/response messaging over data channels
- ``RPCPendingRequest`` — a pending RPC call with timeout
- ``RPCError`` — structured RPC error response

Protocol:
Request:  {"jsonrpc": "2.0", "id": "uuid", "method": "name", "params": {...}}
Response: {"jsonrpc": "2.0", "id": "uuid", "result": {...}}
Error:    {"jsonrpc": "2.0", "id": "uuid", "error": {"code": -1, "message": "..."}}
Notification: {"jsonrpc": "2.0", "method": "event", "params": {...}}  # no id

Usage::

    rpc = DataChannelRPC(pc, channel_label="rpc")

    # Register handlers
    rpc.on("ping", lambda params: {"pong": time.time()})
    rpc.on("chat.send", lambda params: print(params["text"]))

    # Make a call
    result = await rpc.call("ping", {})

    # Send a notification (no response)
    await rpc.notify("user.typing", {"peer_id": "alice"})
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger


class RPCError(Exception):
    """Structured RPC error with code and message."""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[{code}] {message}")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


STANDARD_ERRORS = {
    "parse_error": RPCError(-32700, "Parse error"),
    "invalid_request": RPCError(-32600, "Invalid request"),
    "method_not_found": RPCError(-32601, "Method not found"),
    "invalid_params": RPCError(-32602, "Invalid params"),
    "internal_error": RPCError(-32603, "Internal error"),
    "timeout": RPCError(-32000, "Request timed out"),
}


@dataclass
class RPCPendingRequest:
    """A pending RPC call awaiting a response."""

    id: str
    method: str
    params: Any
    created_at: float = field(default_factory=time.time)
    future: asyncio.Future = field(default_factory=asyncio.Future)


class DataChannelRPC:
    """JSON-RPC 2.0 implementation over WebRTC data channels.

    Supports:
    - Request/response calls with timeout
    - Notifications (fire-and-forget)
    - Method handler registration
    - Middleware for logging, auth, rate limiting
    - Error responses with standard JSON-RPC codes
    """

    def __init__(
        self,
        pc: WebRTCPeerConnection,
        channel_label: str = "rpc",
        request_timeout: float = 30.0,
    ):
        self.pc = pc
        self.channel_label = channel_label
        self.request_timeout = request_timeout
        self._channel: Any = None
        self._handlers: dict[str, Callable] = {}
        self._pending: dict[str, RPCPendingRequest] = {}
        self._middleware: list[Callable] = []
        self._on_notification: list[Callable[[str, Any], None]] = []
        self._logger = logger.getChild(f"rpc-{pc.peer_id}")

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def on(self, method: str, handler: Callable) -> None:
        """Register a handler for an RPC method.

        The handler receives ``params`` and should return the result
        (or raise ``RPCError``).

        Nested methods supported::

            rpc.on("chat.send", handle_chat_send)  # matches "chat.send"
        """
        self._handlers[method] = handler

    def on_notification(self, callback: Callable[[str, Any], None]) -> None:
        """Register a callback for incoming notifications.

        The callback receives ``(method, params)``.
        """
        self._on_notification.append(callback)

    def use(self, middleware: Callable) -> None:
        """Add middleware that runs before handlers.

        Middleware receives ``(method, params)`` and should return
        ``(method, params)`` (possibly modified) or raise RPCError
        to reject.

        Usage::

            async def auth_middleware(method, params):
                if method != "auth.login" and "token" not in params:
                    raise RPCError(-32001, "Not authenticated")
                return method, params

            rpc.use(auth_middleware)
        """
        self._middleware.append(middleware)

    # ------------------------------------------------------------------
    # Making calls
    # ------------------------------------------------------------------

    async def call(
        self,
        method: str,
        params: Any = None,
        timeout: float | None = None,
    ) -> Any:
        """Make an RPC call and wait for the response.

        Args:
            method: Method name to invoke on the remote peer.
            params: Parameters to send.
            timeout: Override the default request timeout.

        Returns:
            The result from the remote handler.

        Raises:
            RPCError: If the remote returns an error or the call times out.
        """
        channel = await self._ensure_channel()
        request_id = uuid.uuid4().hex[:16]
        timeout = timeout or self.request_timeout

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        pending = RPCPendingRequest(
            id=request_id, method=method, params=params
        )
        self._pending[request_id] = pending

        try:
            channel.send(json.dumps(request))
            result = await asyncio.wait_for(
                pending.future, timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            raise STANDARD_ERRORS["timeout"]
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: Any = None) -> None:
        """Send a notification (no response expected).

        Args:
            method: Method name.
            params: Parameters.
        """
        channel = await self._ensure_channel()
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        channel.send(json.dumps(notification))

    # ------------------------------------------------------------------
    # Start receiving
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start listening for incoming RPC messages."""
        await self._ensure_channel()

    async def _ensure_channel(self) -> Any:
        if self._channel is None:
            if self.channel_label in self.pc._data_channels:
                self._channel = self.pc._data_channels[self.channel_label]
            else:
                self._channel = self.pc.create_data_channel(
                    self.channel_label, ordered=True
                )
            self._wire_receiver()
        return self._channel

    def _wire_receiver(self) -> None:
        original = self.pc._on_message

        def _on_message(label: str, data: str | bytes) -> None:
            if label == self.channel_label and isinstance(data, str):
                try:
                    msg = json.loads(data)
                    self._dispatch(msg)
                except json.JSONDecodeError:
                    self._send_error(None, STANDARD_ERRORS["parse_error"])
            if original and label != self.channel_label:
                original(label, data)

        self.pc._on_message = _on_message

    def _dispatch(self, msg: dict[str, Any]) -> None:
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", {})
        has_id = msg_id is not None

        if has_id:
            if msg_id in self._pending:
                pending = self._pending[msg_id]
                if "result" in msg:
                    pending.future.set_result(msg["result"])
                elif "error" in msg:
                    err = msg["error"]
                    pending.future.set_exception(
                        RPCError(err.get("code", -1), err.get("message", ""), err.get("data"))
                    )
                return

            if not method:
                self._send_error(msg_id, STANDARD_ERRORS["invalid_request"])
                return

            asyncio.ensure_future(self._handle_request(msg_id, method, params))

        else:
            if method:
                for cb in self._on_notification:
                    cb(method, params)

    async def _handle_request(
        self, msg_id: str, method: str, params: Any
    ) -> None:
        try:
            for middleware in self._middleware:
                if asyncio.iscoroutinefunction(middleware):
                    method, params = await middleware(method, params)
                else:
                    method, params = middleware(method, params)

            handler = self._handlers.get(method)
            if handler is None:
                self._send_error(msg_id, STANDARD_ERRORS["method_not_found"])
                return

            result = handler(params)
            if asyncio.iscoroutine(result):
                result = await result

            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": result,
            }
            self._channel.send(json.dumps(response))

        except RPCError as e:
            self._send_error(msg_id, e)
        except Exception as e:
            self._logger.exception("handler error for %s", method)
            self._send_error(msg_id, RPCError(-32603, f"Handler error: {e}"))

    def _send_error(
        self, msg_id: str | None, error: RPCError
    ) -> None:
        if msg_id is None or self._channel is None:
            return
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": error.to_dict(),
        }
        try:
            self._channel.send(json.dumps(response))
        except Exception:
            pass


__all__ = [
    "DataChannelRPC",
    "RPCError",
    "RPCPendingRequest",
]
