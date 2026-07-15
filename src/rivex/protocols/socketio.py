from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("rivex.socketio")


class SocketIOServer:
    """Socket.IO protocol adapter for real-time bidirectional communication.

    Implements the Socket.IO protocol (Engine.IO + Socket.IO packets)
    over WebSocket and HTTP long-polling, with room support, events,
    namespaces, and automatic reconnection.

    Usage::

        sio = SocketIOServer()

        @sio.on("connect")
        async def on_connect(sid, environ):
            print(f"Client {sid} connected")

        @sio.on("message")
        async def on_message(sid, data):
            await sio.emit("response", {"from": sid, "data": data})

        @sio.on("disconnect")
        async def on_disconnect(sid):
            print(f"Client {sid} disconnected")

        app.add_middleware(SocketIOMiddleware, server=sio)
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}
        self._namespaces: dict[str, dict[str, list[Callable]]] = {}
        self._sessions: dict[str, SocketIOSession] = {}
        self._rooms: dict[str, set[str]] = {}
        self._middleware: list[Callable] = []

    def on(self, event: str, namespace: str = "/"):
        """Decorator to register an event handler.

        Usage::

            @sio.on("chat_message")
            async def handler(sid, data):
                ...
        """
        def decorator(func: Callable) -> Callable:
            if namespace == "/":
                self._handlers.setdefault(event, []).append(func)
            else:
                self._namespaces.setdefault(namespace, {}).setdefault(event, []).append(func)
            return func
        return decorator

    def use(self, middleware: Callable) -> None:
        self._middleware.append(middleware)

    async def create_session(self, sid: str) -> SocketIOSession:
        session = SocketIOSession(sid)
        self._sessions[sid] = session
        return session

    async def handle_connect(self, sid: str, environ: dict) -> None:
        session = self._sessions.get(sid)
        if not session:
            session = await self.create_session(sid)
        session.connected = True
        for handler in self._handlers.get("connect", []):
            await handler(sid, environ)

    async def handle_event(self, sid: str, event: str, data: Any, namespace: str = "/") -> None:
        handlers = self._handlers.get(event, [])
        if namespace != "/":
            handlers = self._namespaces.get(namespace, {}).get(event, [])
        for handler in handlers:
            await handler(sid, data)

    async def handle_disconnect(self, sid: str) -> None:
        for handler in self._handlers.get("disconnect", []):
            await handler(sid)
        self._sessions.pop(sid, None)
        for room in self._rooms.values():
            room.discard(sid)

    async def emit(
        self,
        event: str,
        data: Any = None,
        room: str | None = None,
        namespace: str = "/",
        skip_sid: str | None = None,
    ) -> None:
        packet = self._encode_packet(event, data, namespace)
        if room:
            sids = list(self._rooms.get(room, set()))
        else:
            sids = list(self._sessions.keys())

        for sid in sids:
            if sid == skip_sid:
                continue
            session = self._sessions.get(sid)
            if session and session.connected:
                await session.send(packet)

    def _encode_packet(self, event: str, data: Any, namespace: str = "/") -> str:
        packet = json.dumps([event, data])
        return f"42{json.dumps(namespace)},{packet}"

    def join_room(self, sid: str, room: str) -> None:
        self._rooms.setdefault(room, set()).add(sid)

    def leave_room(self, sid: str, room: str) -> None:
        self._rooms.get(room, set()).discard(sid)

    @property
    def sessions(self) -> dict[str, SocketIOSession]:
        return dict(self._sessions)

    def connected_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.connected)


class SocketIOSession:
    """Represents a single Socket.IO client connection."""

    def __init__(self, sid: str):
        self.id = sid
        self.connected = False
        self._send_queue: asyncio.Queue = asyncio.Queue()
        self._metadata: dict[str, Any] = {}

    async def send(self, data: str) -> None:
        await self._send_queue.put(data)

    async def receive(self) -> str:
        return await self._send_queue.get()

    def __getitem__(self, key: str) -> Any:
        return self._metadata[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._metadata[key] = value


class SocketIOMiddleware:
    """Middleware that handles Socket.IO protocol over WebSocket.

    Usage::

        app.add_middleware(SocketIOMiddleware, server=sio)
    """

    def __init__(self, server: SocketIOServer, path: str = "/socket.io", app: Any = None):
        self._server = server
        self._path = path

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        path = request_data.get("path", "/")
        if not path.startswith(self._path):
            return await call_next(request_data)

        is_websocket = request_data.get("ws", False)
        if is_websocket:
            return await self._handle_websocket(request_data)
        else:
            return await self._handle_http_longpoll(request_data)

    async def _handle_http_longpoll(self, request_data: dict) -> dict:
        import urllib.parse
        query = request_data.get("query_string", "")
        params = urllib.parse.parse_qs(query)
        transport = params.get("transport", [""])[0]
        sid = params.get("sid", [None])[0]

        if transport == "polling":
            if not sid:
                session_id = str(uuid.uuid4())
                await self._server.create_session(session_id)
                return {
                    "status": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"sid": session_id, "upgrades": ["websocket"], "pingInterval": 25000, "pingTimeout": 20000}),
                }
            else:
                session = self._server._sessions.get(sid)
                if not session:
                    return {"status": 400, "body": "Unknown session"}
                try:
                    data = await asyncio.wait_for(session.receive(), timeout=30)
                    return {"status": 200, "headers": {"Content-Type": "text/plain"}, "body": data}
                except asyncio.TimeoutError:
                    return {"status": 200, "body": "2"}

        elif transport == "websocket":
            return {"status": 400, "body": "Use WebSocket upgrade instead"}

        return {"status": 400, "body": "Unsupported transport"}

    async def _handle_websocket(self, request_data: dict) -> dict:
        sid = str(uuid.uuid4())
        await self._server.create_session(sid)
        await self._server.handle_connect(sid, request_data)

        return {
            "status": 101,
            "ws": True,
            "sid": sid,
        }
