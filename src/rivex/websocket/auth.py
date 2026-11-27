from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from rivex.exceptions.http.exceptions import WebSocketDisconnect


class WSAuthMiddleware:
    def __init__(
        self,
        authenticator: Callable | None = None,
        require_auth: bool = True,
    ):
        self._authenticator = authenticator
        self._require_auth = require_auth

    async def authenticate(self, websocket: Any, message: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve an authentication token from a WebSocket auth message.

        Inspects the inbound auth payload for ``token`` or ``access_token`` and
        delegates to the configured ``authenticator`` callable when present. If
        no authenticator is configured, the raw token is wrapped in a minimal
        ``{"sub": token}`` claim so downstream handlers have something to use.

        Args:
            websocket: The active WebSocket connection; forwarded to the
                authenticator when it expects the socket as a positional
                argument. Not otherwise inspected.
            message: Parsed auth payload received from the client. Only its
                ``token`` / ``access_token`` keys are read.

        Returns:
            A user dict produced by the configured authenticator, a synthetic
            ``{"sub": token}`` dict when no authenticator is set, or ``None``
            when the message carries no token at all.
        """
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
    """Mark a WebSocket handler as requiring authenticated connections.

    Sets the ``_ws_require_auth`` attribute on ``func`` so the surrounding
    authentication middleware can reject unauthenticated requests before the
    handler body runs. The decorator is a no-op beyond the marker and returns
    the original function unchanged.

    Args:
        func: The WebSocket handler to flag. May be sync or async; the
            decorator does not wrap it.

    Returns:
        The same ``func``, returned unmodified so it can still be used as a
        handler.
    """
    func._ws_require_auth = True
    return func
