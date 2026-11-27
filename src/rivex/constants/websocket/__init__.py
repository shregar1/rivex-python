"""``rivex.constants.websocket`` — WebSocket frame, state, and disconnect constant groups package.
"""

from __future__ import annotations

from rivex.constants.websocket.abstraction import IWebSocketConstant
from rivex.constants.websocket.disconnect import WebSocketDisconnectConstant
from rivex.constants.websocket.frame import WebSocketFrameConstant
from rivex.constants.websocket.state import WebSocketStateConstant

__all__ = [
    "IWebSocketConstant",
    "WebSocketFrameConstant",
    "WebSocketStateConstant",
    "WebSocketDisconnectConstant",
]
