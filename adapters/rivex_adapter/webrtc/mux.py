"""
Data channel multiplexer — multiple logical channels over one data channel.

Provides:
- ``DataChannelMux`` — multiplex/demultiplex multiple channels over one
- ``MuxChannel`` — a logical channel within the mux

Protocol:
Each message is prefixed with a 2-byte big-endian channel ID followed
by the payload. The muxer strips/prefixes these IDs transparently.

Usage::

    mux = DataChannelMux(pc, transport_label="mux")

    # Create logical channels
    chat = mux.create_channel("chat")
    control = mux.create_channel("control")

    # Use them like normal data channels
    chat.on_message(lambda data: print(f"Chat: {data}"))
    await mux.send("chat", "Hello!")

    # Or via the channel object
    chat.send("World!")

Extensibility:
    Subclass and override ``encode_frame()`` / ``decode_frame()`` to
    customise the framing protocol.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from dataclasses import dataclass, field
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger


class MuxChannel:
    """A logical channel multiplexed over a single data channel.

    Usage::

        ch = mux.create_channel("chat")
        ch.on_message(lambda data: print(data))
        ch.send("hello")
    """

    def __init__(self, channel_id: int, label: str):
        self.channel_id = channel_id
        self.label = label
        self._on_message: Callable[[str | bytes], None] | None = None
        self._send: Callable[[str | bytes], None] | None = None

    def on_message(self, callback: Callable[[str | bytes], None]) -> None:
        """Register a message callback for this logical channel."""
        self._on_message = callback

    def send(self, data: str | bytes) -> None:
        """Send a message on this logical channel."""
        if self._send is None:
            raise RuntimeError("channel not connected to a mux")
        self._send(data)

    def __repr__(self) -> str:
        return f"MuxChannel(id={self.channel_id}, label={self.label!r})"


class DataChannelMux:
    """Multiplex multiple logical channels over a single data channel.

    Each logical channel gets a unique 16-bit ID. Messages are
    framed with a 2-byte channel ID header.

    Usage::

        mux = DataChannelMux(pc, transport_label="mux")

        chat = mux.create_channel("chat")
        system = mux.create_channel("system")

        chat.on_message(lambda data: print(f"Chat: {data}"))
        system.on_message(lambda data: print(f"Sys: {data}"))

        mux.send("chat", "Hello!")
        mux.send("system", json.dumps({"type": "ping"}))

    All channels are automatically demultiplexed from the single
    underlying data channel.
    """

    HEADER_FORMAT = "!H"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    def __init__(
        self,
        pc: WebRTCPeerConnection,
        transport_label: str = "mux",
    ):
        self.pc = pc
        self.transport_label = transport_label
        self._transport: Any = None
        self._channels: dict[int, MuxChannel] = {}
        self._channels_by_label: dict[str, MuxChannel] = {}
        self._next_id = 1
        self._buffer = bytearray()
        self._logger = logger.getChild(f"mux-{pc.peer_id}")

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def create_channel(self, label: str) -> MuxChannel:
        """Create a new logical channel.

        Args:
            label: Logical channel name (e.g. "chat", "control").

        Returns:
            A ``MuxChannel`` instance.
        """
        if label in self._channels_by_label:
            raise ValueError(f"channel {label!r} already exists")

        channel_id = self._next_id
        self._next_id += 1

        ch = MuxChannel(channel_id, label)
        ch._send = lambda data, cid=channel_id: self._send_raw(cid, data)

        self._channels[channel_id] = ch
        self._channels_by_label[label] = ch
        return ch

    def get_channel(self, label: str) -> MuxChannel | None:
        """Get a logical channel by label."""
        return self._channels_by_label.get(label)

    def remove_channel(self, label: str) -> None:
        """Remove a logical channel."""
        ch = self._channels_by_label.pop(label, None)
        if ch is not None:
            self._channels.pop(ch.channel_id, None)

    def list_channels(self) -> list[str]:
        """List all logical channel labels."""
        return list(self._channels_by_label.keys())

    # ------------------------------------------------------------------
    # Send / receive
    # ------------------------------------------------------------------

    async def send(self, label: str, data: str | bytes) -> None:
        """Send a message on a logical channel."""
        ch = self._channels_by_label.get(label)
        if ch is None:
            raise ValueError(f"channel {label!r} not found")
        ch.send(data)

    async def send_json(self, label: str, data: Any) -> None:
        """Send a JSON message on a logical channel."""
        await self.send(label, json.dumps(data))

    async def start(self) -> None:
        """Start the multiplexer (creates the transport channel)."""
        if self.transport_label in self.pc._data_channels:
            self._transport = self.pc._data_channels[self.transport_label]
        else:
            self._transport = self.pc.create_data_channel(
                self.transport_label, ordered=True
            )

        original_on_message = self.pc._on_message

        def _on_transport_message(label: str, data: str | bytes) -> None:
            if label == self.transport_label:
                self._feed(data)
            if original_on_message and label != self.transport_label:
                original_on_message(label, data)

        self.pc._on_message = _on_transport_message
        self._logger.info(
            "mux started on %s with %d channels",
            self.transport_label, len(self._channels),
        )

    # ------------------------------------------------------------------
    # Internal framing
    # ------------------------------------------------------------------

    def encode_frame(self, channel_id: int, data: bytes) -> bytes:
        """Encode a frame with channel ID header.

        Override to customise framing (e.g. add sequence numbers,
        timestamps, or encryption).
        """
        return struct.pack(self.HEADER_FORMAT, channel_id) + data

    def decode_frame(self, buffer: bytearray) -> tuple[int, bytes, int] | None:
        """Decode a frame from the buffer.

        Returns ``(channel_id, payload, consumed_bytes)`` or ``None``
        if there's not enough data for a complete frame.

        Override for custom framing protocol.
        """
        if len(buffer) < self.HEADER_SIZE:
            return None
        channel_id = struct.unpack(self.HEADER_FORMAT, buffer[:self.HEADER_SIZE])[0]
        payload = bytes(buffer[self.HEADER_SIZE:])
        return channel_id, payload, len(buffer)  # consume everything

    def _send_raw(self, channel_id: int, data: str | bytes) -> None:
        if self._transport is None:
            raise RuntimeError("mux not started, call start() first")
        payload = data.encode() if isinstance(data, str) else data
        frame = self.encode_frame(channel_id, payload)
        self._transport.send(frame)

    def _feed(self, data: str | bytes) -> None:
        if isinstance(data, str):
            data = data.encode()
        self._buffer.extend(data)

        while True:
            result = self.decode_frame(self._buffer)
            if result is None:
                break
            channel_id, payload, consumed = result
            self._buffer = self._buffer[consumed:]

            ch = self._channels.get(channel_id)
            if ch is not None and ch._on_message:
                try:
                    decoded = payload.decode() if isinstance(payload, bytes) else payload
                    ch._on_message(decoded)
                except UnicodeDecodeError:
                    ch._on_message(payload)


__all__ = [
    "DataChannelMux",
    "MuxChannel",
]
