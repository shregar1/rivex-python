"""``rivex.constants.websocket.frame`` — WebSocket frame type string constants.
"""

from __future__ import annotations

from typing import Final

from rivex.constants.websocket.abstraction import IWebSocketConstant


class WebSocketFrameConstant(IWebSocketConstant):
    """WebSocket frame type string constants."""

    TEXT: Final[str] = "text"
    BINARY: Final[str] = "binary"
    PING: Final[str] = "ping"
    PONG: Final[str] = "pong"
    CLOSE: Final[str] = "close"


__all__ = ["WebSocketFrameConstant"]
