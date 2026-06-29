from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from rivex.exceptions import WebSocketDisconnect


class WSAuthMiddleware:
    def __init__(
        self,
        authenticator: Callable | None = None,
        require_auth: bool = True,
    ):
        self._authenticator = authenticator
        self._require_auth = require_auth

    async def authenticate(self, websocket: Any, message: dict[str, Any]) -> dict[str, Any] | None:
        token = message.get("token") or message.get("access_token")
        if not token:
            return None
        if self._authenticator:
            return await self._authenticator(token)
        return {"sub": token}

    async def __call__(self, websocket: Any, receive: Callable) -> dict[str, Any]:
        msg = await receive()
        if msg is None:
            raise WebSocketDisconnect(code=1008, reason="authentication required")
        if isinstance(msg, tuple):
            _, data = msg
        else:
            data = msg
        if isinstance(data, (bytes, bytearray)):
            data = data.decode()
        try:
            payload = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            if self._require_auth:
                raise WebSocketDisconnect(code=1008, reason="invalid auth message") from None
            return {}
        user = await self.authenticate(websocket, payload)
        if user is None and self._require_auth:
            raise WebSocketDisconnect(code=1008, reason="authentication failed")
        return user or {}


def require_ws_auth(func: Callable) -> Callable:
    func._ws_require_auth = True
    return func
