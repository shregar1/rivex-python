"""
Async data channel streams — reader/writer abstraction for
streaming binary data over WebRTC data channels.

``DataChannelReader`` — async iterator yielding chunks from a channel.
``DataChannelWriter`` — async writer that buffers and sends chunks.
``DataChannelStream`` — combined reader+writer for bidirectional use.

Usage::

    # On the sending side
    writer = DataChannelWriter(pc, label="file-transfer")
    await writer.write(b"chunk1")
    await writer.write(b"chunk2")
    await writer.close()

    # On the receiving side
    reader = DataChannelReader(pc, label="file-transfer")
    async for chunk in reader:
        process(chunk)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from rivex_adapter.webrtc.core import logger


class DataChannelWriter:
    """Async writer that sends binary data over a data channel.

    Buffers chunks and sends them as ordered messages.
    Supports backpressure via ``max_buffer_size``.

    Usage::

        writer = DataChannelWriter(pc, label="stream")
        await writer.write(b"data")
        await writer.write(b"more")
        await writer.close()
    """

    def __init__(
        self,
        pc: Any,
        label: str = "stream",
        max_buffer_size: int = 256 * 1024,
        chunk_size: int = 16384,
    ):
        self._pc = pc
        self._label = label
        self._max_buffer_size = max_buffer_size
        self._chunk_size = chunk_size
        self._channel: Any = None
        self._closed = False
        self._buffer_size = 0
        self._ready = asyncio.Event()
        self._logger = logger.getChild(f"dc_writer-{label}")

    async def write(self, data: bytes) -> None:
        """Write a chunk of data. Blocks if buffer is full."""
        await self._ensure_channel()
        offset = 0
        while offset < len(data):
            chunk = data[offset:offset + self._chunk_size]
            offset += len(chunk)
            while self._buffer_size >= self._max_buffer_size:
                await asyncio.sleep(0.01)
            try:
                self._channel.send(chunk)
                self._buffer_size += len(chunk)
            except Exception as e:
                self._logger.error("write error: %s", e)
                raise

    async def close(self) -> None:
        """Close the writer."""
        self._closed = True
        if self._channel:
            try:
                is_closed = getattr(self._channel, "_closed", False) or getattr(self._channel, "readyState", "open") == "closed"
                if not is_closed:
                    self._channel.close()
            except Exception:
                pass

    async def _ensure_channel(self) -> None:
        if self._channel is not None:
            return
        if self._label in self._pc._data_channels:
            self._channel = self._pc._data_channels[self._label]
        else:
            self._channel = self._pc.create_data_channel(
                self._label, ordered=True,
            )


class DataChannelReader:
    """Async reader that yields chunks from a data channel.

    Usage::

        reader = DataChannelReader(pc, label="stream")
        async for chunk in reader:
            print(f"got {len(chunk)} bytes")
    """

    def __init__(self, pc: Any, label: str = "stream"):
        self._pc = pc
        self._label = label
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._original_handler: Any = None
        self._wired = False

    def __aiter__(self) -> DataChannelReader:
        return self

    async def __anext__(self) -> bytes:
        if not self._wired:
            self._wire()
            self._wired = True
        chunk = await self._queue.get()
        if chunk is None:
            raise StopAsyncIteration
        return chunk

    def _wire(self) -> None:
        original = getattr(self._pc, "_on_message", None)

        def on_message(label: str, data: str | bytes) -> None:
            if label == self._label and isinstance(data, bytes):
                self._queue.put_nowait(data)
            if original and label != self._label:
                original(label, data)

        self._pc._on_message = on_message

    def close(self) -> None:
        self._queue.put_nowait(None)


class DataChannelStream:
    """Bidirectional data channel stream (reader + writer).

    Usage::

        stream = DataChannelStream(pc, label="chat")
        await stream.write(b"hello")
        async for msg in stream:
            print(f"received: {msg}")
    """

    def __init__(
        self,
        pc: Any,
        label: str = "stream",
        max_buffer_size: int = 256 * 1024,
    ):
        self.reader = DataChannelReader(pc, label)
        self.writer = DataChannelWriter(pc, label, max_buffer_size)

    async def write(self, data: bytes) -> None:
        await self.writer.write(data)

    def __aiter__(self) -> DataChannelReader:
        return self.reader

    async def __anext__(self) -> bytes:
        return await self.reader.__anext__()

    async def close(self) -> None:
        self.reader.close()
        await self.writer.close()


__all__ = [
    "DataChannelWriter",
    "DataChannelReader",
    "DataChannelStream",
]
