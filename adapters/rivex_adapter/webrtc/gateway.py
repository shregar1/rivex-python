"""
REST API gateway for managing WebRTC resources.

Provides a framework-agnostic router that can be mounted in Rivex,
FastAPI, Starlette, or any ASGI framework.

Endpoints:
- ``GET /webrtc/rooms`` — list active rooms
- ``GET /webrtc/rooms/{room}`` — get room details and peer list
- ``POST /webrtc/rooms/{room}/broadcast`` — broadcast a message to all peers
- ``DELETE /webrtc/rooms/{room}/peers/{peer_id}`` — remove a peer
- ``GET /webrtc/peers`` — list all peer connections
- ``GET /webrtc/peers/{peer_id}`` — get peer connection details and stats
- ``POST /webrtc/peers/{peer_id}/ice-restart`` — trigger ICE restart on a peer
- ``GET /webrtc/conferences`` — list active conferences
- ``GET /webrtc/conferences/{room}`` — get conference details
- ``DELETE /webrtc/conferences/{room}`` — tear down a conference
- ``GET /webrtc/stats`` — global WebRTC statistics
- ``POST /webrtc/turn-config`` — generate TURN server configuration

Usage with Rivex::

    from rivex import Rivex
    from rivex_adapter.webrtc import WebRTCSignaling, WebRTCGateway

    app = Rivex()
    signaling = WebRTCSignaling()
    gateway = WebRTCGateway(signaling)

    gateway.mount(app, prefix="/api")

Usage with FastAPI::

    from fastapi import FastAPI
    app = FastAPI()
    gateway.mount(app, prefix="/api")
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from rivex_adapter.webrtc.signaling import WebRTCSignaling
from rivex_adapter.webrtc.conference import ConferenceBridge
from rivex_adapter.webrtc.media import MediaRecorder
from rivex_adapter.webrtc.infra import TurnConfig, generate_turn_config
from rivex_adapter.webrtc.core import SignalingMessage, SignalingMessageType, logger


@dataclass
class Route:
    """An HTTP route definition."""

    method: str
    path: str
    handler: Callable
    summary: str = ""


@dataclass
class GatewayResponse:
    """Response from a gateway handler."""

    status_code: int = 200
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)


class WebRTCGateway:
    """REST API gateway for WebRTC management.

    Provides HTTP endpoints to inspect and control WebRTC signaling,
    peer connections, conferences, and TURN configuration.

    Framework-agnostic — mount with ``mount()`` for Rivex/FastAPI/Starlette.
    """

    def __init__(
        self,
        signaling: WebRTCSignaling,
        conference: ConferenceBridge | None = None,
    ):
        self.signaling = signaling
        self.conference = conference
        self._routes: list[Route] = []
        self._register_routes()

    def _register_routes(self) -> None:
        self._routes = [
            Route("GET", "/rooms", self._list_rooms, "List active rooms"),
            Route("GET", "/rooms/{room}", self._get_room, "Get room details"),
            Route("POST", "/rooms/{room}/broadcast", self._broadcast, "Broadcast to room"),
            Route("DELETE", "/rooms/{room}/peers/{peer_id}", self._remove_peer, "Remove peer from room"),
            Route("GET", "/peers", self._list_peers, "List all peers"),
            Route("GET", "/peers/{peer_id}", self._get_peer, "Get peer details"),
            Route("POST", "/peers/{peer_id}/ice-restart", self._ice_restart, "Trigger ICE restart"),
            Route("GET", "/conferences", self._list_conferences, "List conferences"),
            Route("GET", "/conferences/{room}", self._get_conference, "Get conference details"),
            Route("DELETE", "/conferences/{room}", self._delete_conference, "Delete conference"),
            Route("GET", "/stats", self._get_stats, "Global statistics"),
            Route("POST", "/turn-config", self._generate_turn, "Generate TURN config"),
        ]

    # ------------------------------------------------------------------
    # Route mounting
    # ------------------------------------------------------------------

    def mount(self, app: Any, prefix: str = "/api") -> None:
        """Mount the gateway routes on an ASGI framework app.

        Supports:
        - Rivex (``app.route()``)
        - FastAPI/Starlette (``app.add_api_route()``, ``app.add_websocket_route()``)
        - Plain ASGI callable
        """
        base = prefix.rstrip("/")

        for route in self._routes:
            path = f"{base}/webrtc{route.path}"

            if hasattr(app, "route"):
                app.route(path, methods=[route.method])(self._wrap_handler(route))
            elif hasattr(app, "add_api_route"):
                app.add_api_route(path, self._wrap_handler(route), methods=[route.method])
            elif callable(app):
                pass

        if hasattr(app, "add_api_route"):
            @app.get(f"{base}/webrtc/openapi.json")
            async def _openapi():
                return self._generate_openapi(base)

    async def _handle_request(
        self, method: str, path: str, params: dict[str, str], body: Any
    ) -> GatewayResponse:
        for route in self._routes:
            if route.method.upper() != method.upper():
                continue
            match = self._match_path(route.path, path)
            if match is not None:
                kwargs = {**match, **params}
                if body is not None:
                    kwargs["body"] = body
                try:
                    result = await route.handler(**kwargs)
                    if isinstance(result, GatewayResponse):
                        return result
                    return GatewayResponse(body=result)
                except Exception as e:
                    return GatewayResponse(
                        status_code=500,
                        body={"error": str(e)},
                    )
        return GatewayResponse(status_code=404, body={"error": "not found"})

    def _match_path(
        self, pattern: str, path: str
    ) -> dict[str, str] | None:
        pattern_parts = pattern.strip("/").split("/")
        path_parts = path.strip("/").split("/")
        if len(pattern_parts) != len(path_parts):
            return None
        params: dict[str, str] = {}
        for pp, pv in zip(pattern_parts, path_parts):
            if pp.startswith("{") and pp.endswith("}"):
                params[pp[1:-1]] = pv
            elif pp != pv:
                return None
        return params

    def _wrap_handler(self, route: Route) -> Callable:
        async def _handler(**kwargs: Any) -> Any:
            body = kwargs.pop("body", None)
            path = route.path
            for key, value in list(kwargs.items()):
                path = path.replace(f"{{{key}}}", str(value))
            response = await self._handle_request(route.method, path, {}, body)
            return response.body
        return _handler

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _list_rooms(self, **kwargs: Any) -> list[dict[str, Any]]:
        rooms = self.signaling.get_rooms()
        result = []
        for room in rooms:
            peers = self.signaling.get_room_peers(room)
            result.append({
                "name": room,
                "peer_count": len(peers),
                "peers": peers,
            })
        return result

    async def _get_room(self, room: str, **kwargs: Any) -> dict[str, Any]:
        peers = self.signaling.get_room_peers(room)
        return {
            "name": room,
            "peer_count": len(peers),
            "peers": [
                {
                    "id": pid,
                    "metadata": self.signaling.get_peer_metadata(pid),
                }
                for pid in peers
            ],
        }

    async def _broadcast(self, room: str, body: Any = None, **kwargs: Any) -> dict[str, Any]:
        data = body if body is not None else {}
        await self.signaling.broadcast(room, data)
        return {"status": "ok", "room": room}

    async def _remove_peer(
        self, room: str, peer_id: str, **kwargs: Any
    ) -> dict[str, Any]:
        peers = self.signaling.get_room_peers(room)
        if peer_id not in peers:
            return {"status": "error", "detail": f"peer {peer_id!r} not in room {room!r}"}
        self.signaling._leave_room(room, peer_id)
        return {"status": "ok", "room": room, "peer_id": peer_id}

    async def _list_peers(self, **kwargs: Any) -> list[dict[str, Any]]:
        peers = []
        for room in self.signaling.get_rooms():
            for pid in self.signaling.get_room_peers(room):
                pc = self.signaling.get_peer(pid)
                peers.append({
                    "id": pid,
                    "room": room,
                    "connected": pc is not None and pc.connection_state == "connected",
                    "state": pc.connection_state if pc else "unknown",
                    "metadata": self.signaling.get_peer_metadata(pid),
                })
        return peers

    async def _get_peer(self, peer_id: str, **kwargs: Any) -> dict[str, Any]:
        pc = self.signaling.get_peer(peer_id)
        if pc is None:
            return {"status": "error", "detail": f"peer {peer_id!r} not found"}
        return {
            "id": peer_id,
            "connection_state": pc.connection_state,
            "ice_connection_state": pc.ice_connection_state,
            "data_channels": list(pc._data_channels.keys()),
        }

    async def _ice_restart(self, peer_id: str, **kwargs: Any) -> dict[str, Any]:
        pc = self.signaling.get_peer(peer_id)
        if pc is None:
            return {"status": "error", "detail": f"peer {peer_id!r} not found"}
        import asyncio
        offer = await pc.ice_restart()
        return {"status": "ok", "offer": offer}

    async def _list_conferences(self, **kwargs: Any) -> list[dict[str, Any]]:
        if self.conference is None:
            return []
        return [
            {
                "room": self.conference.room,
                "peer_count": len(self.conference.get_peers()),
                "connection_count": len(self.conference.get_connections()),
            }
        ]

    async def _get_conference(self, room: str, **kwargs: Any) -> dict[str, Any]:
        if self.conference is None:
            return {"status": "error", "detail": "no conference configured"}
        return self.conference.get_stats()

    async def _delete_conference(self, room: str, **kwargs: Any) -> dict[str, Any]:
        if self.conference is None:
            return {"status": "error", "detail": "no conference configured"}
        await self.conference.close()
        return {"status": "ok", "detail": f"conference {room!r} deleted"}

    async def _get_stats(self, **kwargs: Any) -> dict[str, Any]:
        rooms = self.signaling.get_rooms()
        total_peers = sum(
            len(self.signaling.get_room_peers(r)) for r in rooms
        )
        return {
            "rooms": len(rooms),
            "total_peers": total_peers,
            "rooms_list": rooms,
            "timestamp": time.time(),
        }

    async def _generate_turn(
        self, body: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        config_data = body or {}
        tc = TurnConfig(
            realm=config_data.get("realm", "example.com"),
            users=config_data.get("users", {}),
            use_auth_secret=config_data.get("use_auth_secret", False),
            auth_secret=config_data.get("auth_secret", ""),
        )
        return {
            "ice_servers": [
                {
                    "urls": s.urls,
                    "username": s.username,
                    "credential": s.credential,
                }
                for s in tc.to_ice_servers()
            ],
            "coturn_config": tc.to_coturn_config(),
        }

    def _generate_openapi(self, base: str) -> dict[str, Any]:
        paths: dict[str, Any] = {}
        for route in self._routes:
            path = f"{base}/webrtc{route.path}"
            paths[path] = {
                route.method.lower(): {
                    "summary": route.summary,
                    "responses": {"200": {"description": "Success"}},
                }
            }
        return {
            "openapi": "3.0.0",
            "info": {"title": "WebRTC Gateway", "version": "1.0.0"},
            "paths": paths,
        }


__all__ = [
    "WebRTCGateway",
    "GatewayResponse",
]
