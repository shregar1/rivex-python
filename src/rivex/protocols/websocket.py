from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import struct
from enum import IntEnum
from typing import Any

from rivex.native._compat import HAS_CORE
from rivex.native._compat import rc as _rc
from rivex.exceptions.http.exceptions import WebSocketDisconnect


class WebSocketState(IntEnum):
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


class WebSocket:
    """Low-level asyncio-Stream-based WebSocket.

    .. deprecated::
        This class is the legacy implementation that speaks the
        WebSocket protocol over a raw ``asyncio.StreamReader`` /
        ``StreamWriter``. The main path in ``applications.py`` uses
        ``rivex.websockets.WebSocket`` (the async wrapper over
        ``rivex_core.PyWebSocket``) — which is what the
        ``@app.websocket`` decorator and ``add_websocket_route``
        dispatch through.

        This class is kept only as a typing reference for the
        ``ConnectionManager`` helper in ``rivex.ws``. New code
        should import from ``rivex.websockets`` instead.

    The constructor accepts the (scope, reader, writer) triple for
    backwards compatibility, but also tolerates a single ``raw``
    argument (the Rust ``PyWebSocket``) to match the
    ``websockets.py`` call signature, so the two modules' types
    don't collide at import time.
    """

    def __init__(
        self,
        scope_or_raw: Any,
        reader: asyncio.StreamReader | None = None,
        writer: asyncio.StreamWriter | None = None,
    ):
        # Two-arg call form: WebSocket(raw_ws) — same shape as
        # rivex.websockets.WebSocket. We don't have a real reader/
        # writer in that case; the wrapper provides them lazily.
        if reader is None and writer is None:
            self.scope: dict[str, Any] = {}
            self._raw = scope_or_raw
            self._reader = None  # type: ignore[assignment]
            self._writer = None  # type: ignore[assignment]
        else:
            self.scope = scope_or_raw
            self._raw = None
            self._reader = reader
            self._writer = writer

        self.client_state = WebSocketState.CONNECTING
        self.path = self.scope.get("path", "/")
        self.query_string = self.scope.get("query_string", "")
        self.path_params: dict[str, str] = self.scope.get("path_params", {})
        self.headers: dict[str, str] = self.scope.get("headers", {})

    async def accept(self, subprotocol: str | None = None) -> None:
        """Complete the WebSocket handshake with the client.

        Builds the ``101 Switching Protocols`` response, including the
        computed ``Sec-WebSocket-Accept`` value and an optional
        ``Sec-WebSocket-Protocol`` line, writes it to the underlying
        stream, and flips :attr:`client_state` to ``CONNECTED``.

        Args:
            subprotocol: Optional subprotocol identifier the caller
                selected during the handshake.
        """
        key = self.headers.get("sec-websocket-key", "")
        accept_key = _compute_accept_key(key)

        lines = [
            "HTTP/1.1 101 Switching Protocols",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Accept: {accept_key}",
        ]
        if subprotocol:
            lines.append(f"Sec-WebSocket-Protocol: {subprotocol}")
        lines.append("")
        lines.append("")
        self._writer.write("\r\n".join(lines).encode())
        await self._writer.drain()
        self.client_state = WebSocketState.CONNECTED

    async def receive_text(self) -> str:
        """Read the next text frame and decode it as UTF-8.

        Returns:
            The decoded string payload.

        Raises:
            WebSocketDisconnect: When the peer has closed the
                connection (i.e. the underlying read returns ``None``).
        """
        data = await self._read_frame()
        if data is None:
            raise WebSocketDisconnect()
        return data.decode("utf-8")

    async def receive_bytes(self) -> bytes:
        """Read the next binary frame.

        Returns:
            The raw payload bytes.

        Raises:
            WebSocketDisconnect: When the peer has closed the
                connection.
        """
        data = await self._read_frame()
        if data is None:
            raise WebSocketDisconnect()
        return data

    async def receive_json(self, mode: str = "text") -> Any:
        """Read a frame and parse it as JSON.

        Args:
            mode: Either ``"text"`` (read a text frame and decode the
                JSON string) or ``"binary"`` (read a binary frame and
                parse the bytes as JSON). Defaults to ``"text"``.

        Returns:
            The decoded Python value (typically a dict or list).

        Raises:
            WebSocketDisconnect: When the peer has closed the
                connection.
        """
        if mode == "text":
            text = await self.receive_text()
            return json.loads(text)
        data = await self.receive_bytes()
        return json.loads(data)

    async def send_text(self, data: str) -> None:
        """Send a text frame to the peer.

        Uses the Rust encoder when available; otherwise falls back to
        the pure-Python :meth:`_write_frame` path.

        Args:
            data: The UTF-8 text payload to deliver.
        """
        if HAS_CORE:
            self._writer.write(_rc.ws_encode_text(data))
            await self._writer.drain()
        else:
            await self._write_frame(data.encode("utf-8"), opcode=0x1)

    async def send_bytes(self, data: bytes) -> None:
        """Send a binary frame to the peer.

        Uses the Rust encoder when available; otherwise falls back to
        the pure-Python :meth:`_write_frame` path.

        Args:
            data: The raw payload bytes to deliver.
        """
        if HAS_CORE:
            self._writer.write(_rc.ws_encode_binary(data))
            await self._writer.drain()
        else:
            await self._write_frame(data, opcode=0x2)

    async def send_json(self, data: Any, mode: str = "text") -> None:
        """Serialize ``data`` to JSON and send it as a text or binary frame.

        Args:
            data: Any value accepted by ``json.dumps`` — typically a
                dict or list.
            mode: Either ``"text"`` (send a text frame containing the
                JSON string) or ``"binary"`` (send a binary frame
                containing the UTF-8 bytes). Defaults to ``"text"``.
        """
        text = json.dumps(data)
        if mode == "text":
            await self.send_text(text)
        else:
            await self.send_bytes(text.encode("utf-8"))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Send a Close frame and shut the connection down.

        Uses the normal close code (1000) by default. Exceptions during
        the close handshake or the writer teardown are swallowed so the
        caller can use this as a finalizer without a try/except.

        Args:
            code: WebSocket close status code to send.
            reason: Optional human-readable close reason.
        """
        try:
            if HAS_CORE:
                self._writer.write(_rc.ws_encode_close(code, reason))
                await self._writer.drain()
            else:
                payload = struct.pack("!H", code) + reason.encode("utf-8")
                await self._write_frame(payload, opcode=0x8)
        except Exception:
            pass
        self.client_state = WebSocketState.DISCONNECTED
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass

    async def _read_frame(self) -> bytes | None:
        """Dispatch to the Rust or pure-Python frame reader.

        Returns:
            The decoded payload for a data frame, or ``None`` when the
            connection has been closed cleanly.
        """
        if HAS_CORE:
            return await self._read_frame_rust()
        return await self._read_frame_py()

    async def _read_frame_rust(self) -> bytes | None:
        """Read a single frame using the Rust ``rivex_core`` decoder.

        Mirrors the wire layout of RFC 6455: a 1-byte header followed
        by a 7-bit length, optional 16/64-bit extended length, optional
        mask, and the payload. Control frames (PING/PONG/CLOSE) are
        handled transparently: pings are auto-answered, pongs are
        dropped, and a close frame raises :class:`WebSocketDisconnect`.

        Returns:
            The decoded payload, or ``None`` if the connection was
            closed cleanly.

        Raises:
            WebSocketDisconnect: When a close frame is received.
        """
        try:
            first_byte = await self._reader.readexactly(1)
            second_byte = await self._reader.readexactly(1)
        except (asyncio.IncompleteReadError, ConnectionError):
            self.client_state = WebSocketState.DISCONNECTED
            return None

        length = second_byte[0] & 0x7F
        buf = bytearray()
        buf.extend(first_byte)
        buf.extend(second_byte)

        if length == 126:
            raw = await self._reader.readexactly(2)
            buf.extend(raw)
        elif length == 127:
            raw = await self._reader.readexactly(8)
            buf.extend(raw)

        masked = (second_byte[0] & 0x80) != 0
        if masked:
            mask_key = await self._reader.readexactly(4)
            buf.extend(mask_key)

        payload_len = self._decode_payload_length(second_byte[0], buf[2:] if length < 126 else buf[2:])
        payload = await self._reader.readexactly(payload_len)
        buf.extend(payload)

        result = _rc.ws_decode_frame(bytes(buf))
        if result is None:
            self.client_state = WebSocketState.DISCONNECTED
            return None

        opcode, frame_payload, _consumed = result
        if opcode == 8:
            self.client_state = WebSocketState.DISCONNECTED
            close_code = 1000
            close_reason = ""
            if len(frame_payload) >= 2:
                close_code = struct.unpack("!H", frame_payload[:2])[0]
                close_reason = frame_payload[2:].decode("utf-8", errors="replace")
            raise WebSocketDisconnect(code=close_code, reason=close_reason)
        if opcode == 9:
            payload_bytes = bytes(frame_payload)
            self._writer.write(_rc.ws_encode_binary(payload_bytes) if HAS_CORE else _build_pong(payload_bytes))
            await self._writer.drain()
            return await self._read_frame()
        if opcode == 10:
            return await self._read_frame()
        return bytes(frame_payload)

    def _decode_payload_length(self, second_byte: int, extended: bytes) -> int:
        """Decode the WebSocket payload length from a frame header.

        Implements the RFC 6455 length encoding: a 7-bit length in
        ``second_byte`` selects between the inline length, a 16-bit
        extended length, or a 64-bit extended length.

        Args:
            second_byte: The second byte of the frame header (the one
                carrying the MASK bit and the 7-bit length).
            extended: The bytes following ``second_byte`` — the
                2- or 8-byte extended length when applicable.

        Returns:
            The decoded payload length in bytes.
        """
        length = second_byte & 0x7F
        if length == 126:
            return struct.unpack("!H", extended[:2])[0]
        if length == 127:
            return struct.unpack("!Q", extended[:8])[0]
        return length

    async def _read_frame_py(self) -> bytes | None:
        """Read a single frame using the pure-Python implementation.

        Used when ``rivex_core`` is not available. Mirrors
        :meth:`_read_frame_rust` exactly from the caller's perspective,
        including auto-reply on PING and raising
        :class:`WebSocketDisconnect` on CLOSE.

        Returns:
            The decoded payload, or ``None`` on a clean close.

        Raises:
            WebSocketDisconnect: When a close frame is received.
        """
        try:
            first_byte = await self._reader.readexactly(1)
            second_byte = await self._reader.readexactly(1)
        except (asyncio.IncompleteReadError, ConnectionError):
            self.client_state = WebSocketState.DISCONNECTED
            return None

        opcode = first_byte[0] & 0x0F
        masked = (second_byte[0] & 0x80) != 0
        length = second_byte[0] & 0x7F

        if length == 126:
            raw = await self._reader.readexactly(2)
            length = struct.unpack("!H", raw)[0]
        elif length == 127:
            raw = await self._reader.readexactly(8)
            length = struct.unpack("!Q", raw)[0]

        mask_key = b""
        if masked:
            mask_key = await self._reader.readexactly(4)

        payload = await self._reader.readexactly(length)

        if masked and mask_key:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

        if opcode == 0x8:
            self.client_state = WebSocketState.DISCONNECTED
            close_code = 1000
            close_reason = ""
            if len(payload) >= 2:
                close_code = struct.unpack("!H", payload[:2])[0]
                close_reason = payload[2:].decode("utf-8", errors="replace")
            raise WebSocketDisconnect(code=close_code, reason=close_reason)

        if opcode == 0x9:
            await self._write_frame(payload, opcode=0xA)
            return await self._read_frame()

        if opcode == 0xA:
            return await self._read_frame()

        return payload

    async def _write_frame(self, data: bytes, opcode: int = 0x1) -> None:
        """Encode ``data`` as a single unmasked WebSocket frame and write it.

        Implements the RFC 6455 frame layout: a FIN bit plus the
        supplied ``opcode`` in the first byte, the 7-bit /
        16-bit / 64-bit length prefix as appropriate, and the raw
        payload. The resulting frame is written to the underlying
        writer and drained so the caller can continue immediately.

        Args:
            data: Payload bytes to send.
            opcode: WebSocket opcode (``0x1`` for text, ``0x2`` for
                binary, ``0x8`` for close, ``0x9`` for ping,
                ``0xA`` for pong). Defaults to ``0x1`` (text).
        """
        frame = bytearray()
        frame.append(0x80 | opcode)

        length = len(data)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(127)
            frame.extend(struct.pack("!Q", length))

        frame.extend(data)
        self._writer.write(bytes(frame))
        await self._writer.drain()


_WS_MAGIC = b"258EAFA5-E914-47DA-95CA-5AB53CF86C11"


def _compute_accept_key(key: str) -> str:
    sha1 = hashlib.sha1(key.encode() + _WS_MAGIC).digest()
    return base64.b64encode(sha1).decode()


def is_websocket_upgrade(headers: list[tuple[str, str]]) -> bool:
    if HAS_CORE:
        return bool(_rc.is_websocket_upgrade(headers))
    upgrade = False
    connection_upgrade = False
    for k, v in headers:
        key = k.lower()
        if key == "upgrade" and v.lower() == "websocket":
            upgrade = True
        if key == "connection" and "upgrade" in v.lower():
            connection_upgrade = True
    return upgrade and connection_upgrade


def _build_pong(payload: bytes) -> bytes:
    frame = bytearray()
    frame.append(0x8A)
    length = len(payload)
    if length < 126:
        frame.append(length)
    elif length < 65536:
        frame.append(126)
        frame.extend(struct.pack("!H", length))
    else:
        frame.append(127)
        frame.extend(struct.pack("!Q", length))
    frame.extend(payload)
    return bytes(frame)
