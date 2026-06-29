from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from rivex.exceptions import WebSocketDisconnect


class RPCServer:
    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, method: str, handler: Callable) -> None:
        self._handlers[method] = handler

    async def handle_message(self, websocket: Any, message: dict[str, Any]) -> None:
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
        msg = json.dumps({"type": "rpc:response", "id": req_id, "result": result})
        await websocket.send(msg)

    async def _send_error(self, websocket: Any, req_id: str, code: int, message: str) -> None:
        msg = json.dumps({"type": "rpc:error", "id": req_id, "code": code, "message": message})
        await websocket.send(msg)


class RPCClient:
    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout
        self._pending: dict[str, asyncio.Future] = {}
        self._seq = 0

    def _next_id(self) -> str:
        self._seq += 1
        return f"rpc:{self._seq}:{uuid.uuid4().hex[:8]}"

    async def call(self, send: Callable, receive: Callable, method: str, params: Any = None) -> Any:
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
    def decorator(func: Callable) -> Callable:
        func._rpc_method = name or func.__name__
        return func

    return decorator
