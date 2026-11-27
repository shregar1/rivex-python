"""``rivex.enums.websocket.disconnect`` — WebSocket disconnect code enum.
"""

from __future__ import annotations

from rivex.constants.websocket.disconnect import WebSocketDisconnectConstant
from rivex.enums.websocket.abstraction import IWebSocketEnum


class DisconnectCode(int, IWebSocketEnum):
    """WebSocket disconnect code Enum built from ``WebSocketDisconnectConstant`` constants."""

    NORMAL = WebSocketDisconnectConstant.NORMAL
    GOING_AWAY = WebSocketDisconnectConstant.GOING_AWAY
    PROTOCOL_ERROR = WebSocketDisconnectConstant.PROTOCOL_ERROR
    UNSUPPORTED_DATA = WebSocketDisconnectConstant.UNSUPPORTED_DATA
    POLICY_VIOLATION = WebSocketDisconnectConstant.POLICY_VIOLATION
    TOO_BIG = WebSocketDisconnectConstant.TOO_BIG
    SERVER_ERROR = WebSocketDisconnectConstant.SERVER_ERROR


__all__ = ["DisconnectCode"]
