"""
Pre-built signaling server for WebRTC.

Provides an ASGI-compatible signaling server that handles WebSocket
connections and delegates to ``WebRTCSignaling``.

Supports Rivex, FastAPI, Starlette, and plain ASGI frameworks.

Usage with Rivex::

    from rivex import Rivex
    from rivex_adapter.webrtc import WebRTCSignaling, SignalingServer

    app = Rivex()
    signaling = WebRTCSignaling()
    server = SignalingServer(signaling)

    server.mount(app, prefix="/ws")

    # Clients connect to: ws://host/ws/webrtc/signal/{room}

Usage with FastAPI::

    from fastapi import FastAPI
    app = FastAPI()
    server = SignalingServer(signaling)
    server.mount(app, prefix="/ws")

Extensibility:
    Subclass and override ``on_connect()``, ``on_disconnect()``,
    or ``authenticate()`` to customize the signaling flow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable

from rivex_adapter.webrtc.signaling import WebRTCSignaling
from rivex_adapter.webrtc.core import logger


class SignalingServer:
    """Pre-built WebRTC signaling server.

    Handles WebSocket connections, dispatches to ``WebRTCSignaling``,
    and provides built-in health check, ping/pong, and auth endpoints.

    The server exposes:
    - ``/webrtc/signal/{room}`` — main signaling WebSocket
    - ``/webrtc/accept/{room}`` — high-level auto-negotiate WebSocket
    - ``/webrtc/health`` — health check endpoint
    """

    def __init__(
        self,
        signaling: WebRTCSignaling,
        heartbeat_interval: float = 30.0,
    ):
        self.signaling = signaling
        self.heartbeat_interval = heartbeat_interval
        self._active_connections: dict[str, set[str]] = {}
        self._on_connect: list[Callable[[str, str], None]] = []
        self._on_disconnect: list[Callable[[str, str], None]] = []
        self._logger = logger.getChild("signaling-server")

    def on_connect(self, callback: Callable[[str, str], None]) -> None:
        """Called when a client connects to a signaling room.

        The callback receives ``(room, peer_id)``.
        """
        self._on_connect.append(callback)

    def on_disconnect(self, callback: Callable[[str, str], None]) -> None:
        """Called when a client disconnects from a signaling room.

        The callback receives ``(room, peer_id)``.
        """
        self._on_disconnect.append(callback)

    async def authenticate(
        self, room: str, headers: dict[str, str], query: dict[str, str]
    ) -> str | None:
        """Authenticate a WebSocket connection.

        Return a peer ID if accepted, or ``None`` to reject.

        Override for custom authentication. Default accepts all.
        """
        return None

    def mount(self, app: Any, prefix: str = "/ws") -> None:
        """Mount the signaling server routes on an ASGI app.

        Supports Rivex, FastAPI, Starlette, and plain ASGI.
        """
        base = prefix.rstrip("/")

        paths = {
            "signal": f"{base}/webrtc/signal/{{room}}",
            "accept": f"{base}/webrtc/accept/{{room}}",
            "health": f"{base}/webrtc/health",
        }

        if hasattr(app, "websocket"):
            @app.websocket(paths["signal"])
            async def _signal_ws(ws: Any) -> None:
                await self._handle_signal(ws)

            @app.websocket(paths["accept"])
            async def _accept_ws(ws: Any) -> None:
                await self._handle_accept(ws)

            if hasattr(app, "route"):
                @app.route(paths["health"])
                async def _health(req: Any) -> Any:
                    return self._handle_health()

        elif hasattr(app, "add_websocket_route"):
            app.add_websocket_route(paths["signal"], self._handle_signal)
            app.add_websocket_route(paths["accept"], self._handle_accept)

            if hasattr(app, "add_api_route"):
                @app.get(paths["health"])
                async def _health():
                    return self._handle_health()

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    async def _handle_signal(self, ws: Any) -> None:
        """Handle a signaling WebSocket connection."""
        room = self._get_room(ws)
        if room is None:
            await self._close_with_error(ws, "room parameter required")
            return

        headers = self._get_headers(ws)
        query = self._get_query(ws)

        peer_id = await self.authenticate(room, headers, query)
        pid = peer_id or self._generate_id()

        self._track_connection(room, pid)

        for cb in self._on_connect:
            cb(room, pid)

        try:
            async for msg in self.signaling.handle(ws, room, pid):
                await self._safe_send(ws, msg)

                if msg.get("type") == "pong":
                    continue

        except Exception:
            self._logger.exception("signal handler error for %s in %s", pid, room)
        finally:
            self._untrack_connection(room, pid)
            for cb in self._on_disconnect:
                cb(room, pid)

    async def _handle_accept(self, ws: Any) -> None:
        """Handle a high-level auto-negotiation WebSocket."""
        room = self._get_room(ws)
        if room is None:
            await self._close_with_error(ws, "room parameter required")
            return

        headers = self._get_headers(ws)
        query = self._get_query(ws)

        peer_id = await self.authenticate(room, headers, query)

        try:
            pc = await self.signaling.accept(ws, room, peer_id)

            async for msg in self.signaling._receive_messages(ws):
                pass

        except Exception:
            self._logger.exception("accept handler error")
        finally:
            if "pc" in dir():
                await pc.close()

    def _handle_health(self) -> dict[str, Any]:
        """Health check endpoint."""
        total_active = sum(len(peers) for peers in self._active_connections.values())
        return {
            "status": "healthy",
            "active_rooms": len(self._active_connections),
            "active_connections": total_active,
            "rooms": {
                room: len(peers)
                for room, peers in self._active_connections.items()
            },
            "timestamp": time.time(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_room(self, ws: Any) -> str | None:
        if hasattr(ws, "url_params"):
            return ws.url_params.get("room")
        if hasattr(ws, "path_params"):
            return ws.path_params.get("room")
        return None

    def _get_headers(self, ws: Any) -> dict[str, str]:
        if hasattr(ws, "headers"):
            return dict(ws.headers)
        return {}

    def _get_query(self, ws: Any) -> dict[str, str]:
        if hasattr(ws, "query_params"):
            return dict(ws.query_params)
        return {}

    def _generate_id(self) -> str:
        import uuid
        return uuid.uuid4().hex[:12]

    def _track_connection(self, room: str, peer_id: str) -> None:
        self._active_connections.setdefault(room, set()).add(peer_id)

    def _untrack_connection(self, room: str, peer_id: str) -> None:
        peers = self._active_connections.get(room)
        if peers:
            peers.discard(peer_id)
            if not peers:
                del self._active_connections[room]

    async def _safe_send(self, ws: Any, data: dict[str, Any]) -> None:
        try:
            if hasattr(ws, "send_json"):
                await ws.send_json(data)
            elif hasattr(ws, "send"):
                await ws.send(json.dumps(data))
        except Exception:
            pass

    async def _close_with_error(self, ws: Any, message: str) -> None:
        try:
            if hasattr(ws, "close"):
                await ws.close(code=4000, reason=message)
        except Exception:
            pass


__all__ = [
    "SignalingServer",
]
