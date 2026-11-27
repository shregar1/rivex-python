"""``rivex.enums.websocket.frame`` — WebSocket frame type enum.
"""

from __future__ import annotations

from rivex.constants.websocket.frame import WebSocketFrameConstant
from rivex.enums.websocket.abstraction import IWebSocketEnum


class FrameType(str, IWebSocketEnum):
    """WebSocket frame type Enum built from ``WebSocketFrameConstant`` constants."""

    TEXT = WebSocketFrameConstant.TEXT
    BINARY = WebSocketFrameConstant.BINARY
    PING = WebSocketFrameConstant.PING
    PONG = WebSocketFrameConstant.PONG
    CLOSE = WebSocketFrameConstant.CLOSE


__all__ = ["FrameType"]
