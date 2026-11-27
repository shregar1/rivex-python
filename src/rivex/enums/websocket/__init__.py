"""``rivex.enums.websocket`` — WebSocket frame, state, and disconnect enums package.
"""

from __future__ import annotations

from rivex.enums.websocket.abstraction import IWebSocketEnum
from rivex.enums.websocket.disconnect import DisconnectCode
from rivex.enums.websocket.frame import FrameType
from rivex.enums.websocket.state import ConnectionState

__all__ = ["IWebSocketEnum", "FrameType", "ConnectionState", "DisconnectCode"]
