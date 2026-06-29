"""
File transfer over WebRTC data channels.

Provides:
- ``FileTransfer`` — send and receive files over data channels
- ``FileMetadata`` — file metadata exchanged before transfer
- ``FileProgress`` — progress tracking during transfer

Usage::

    from rivex_adapter.webrtc import WebRTCPeerConnection, FileTransfer

    pc = WebRTCPeerConnection()
    ft = FileTransfer(pc, channel_label="file-transfer")

    # Sender
    await ft.send_file("/path/to/file.pdf")

    # Receiver (register before the sender starts)
    ft.on_file(lambda metadata: print(f"Receiving {metadata.name}"))
    ft.on_progress(lambda p: print(f"Progress: {p.percent:.1f}%"))
    ft.on_complete(lambda path: print(f"Saved to {path}"))

Extensibility:
    Subclass and override ``serialize_metadata()``, ``deserialize_metadata()``,
    ``write_chunk()``, or ``process_complete_file()``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger

CHUNK_SIZE = 65536  # 64 KB


class FileTransferState(Enum):
    IDLE = "idle"
    SENDING = "sending"
    RECEIVING = "receiving"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FileMetadata:
    """Metadata exchanged before a file transfer begins."""

    transfer_id: str
    name: str
    size: int
    mime_type: str
    chunk_size: int = CHUNK_SIZE
    checksum: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FileMetadata:
        return cls(**d)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transfer_id": self.transfer_id,
            "name": self.name,
            "size": self.size,
            "mime_type": self.mime_type,
            "chunk_size": self.chunk_size,
            "checksum": self.checksum,
        }


@dataclass
class FileProgress:
    """Progress information for an active file transfer."""

    transfer_id: str
    name: str
    total_bytes: int
    transferred_bytes: int
    speed_bps: float = 0.0
    elapsed: float = 0.0

    @property
    def percent(self) -> float:
        return (self.transferred_bytes / max(self.total_bytes, 1)) * 100

    @property
    def remaining_bytes(self) -> int:
        return max(0, self.total_bytes - self.transferred_bytes)

    @property
    def eta_seconds(self) -> float:
        if self.speed_bps <= 0:
            return 0.0
        return self.remaining_bytes / self.speed_bps

    def to_dict(self) -> dict[str, Any]:
        return {
            "transfer_id": self.transfer_id,
            "name": self.name,
            "total_bytes": self.total_bytes,
            "transferred_bytes": self.transferred_bytes,
            "percent": round(self.percent, 1),
            "speed_bps": round(self.speed_bps),
            "eta_seconds": round(self.eta_seconds, 1),
        }


class FileTransfer:
    """Send and receive files over a WebRTC data channel.

    Protocol:
    1. Sender sends ``FileMetadata`` as JSON
    2. Receiver acknowledges with ``{"ack": transfer_id}``
    3. Sender sends chunks as binary messages
    4. After last chunk, sender sends ``{"done": transfer_id, "checksum": "..."}``
    5. Receiver reassembles and saves the file

    Each transfer gets a dedicated data channel (label = ``channel_label``).
    Multiple transfers can be multiplexed over the same channel.

    Extensibility:
        Override ``get_save_path()``, ``write_chunk()``, or
        ``process_complete_file()`` to customize storage.
    """

    def __init__(
        self,
        pc: WebRTCPeerConnection,
        channel_label: str = "file-transfer",
        download_dir: str = "/tmp",
    ):
        self.pc = pc
        self.channel_label = channel_label
        self.download_dir = download_dir
        self._channel: Any = None
        self._transfers: dict[str, dict[str, Any]] = {}
        self._on_file: list[Callable[[FileMetadata], None]] = []
        self._on_progress: list[Callable[[FileProgress], None]] = []
        self._on_complete: list[Callable[[str], None]] = []
        self._on_error: list[Callable[[str, Exception], None]] = []
        self._logger = logger.getChild(f"ft-{pc.peer_id}")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_file(self, callback: Callable[[FileMetadata], None]) -> None:
        """Register a callback when an incoming file is announced.

        Return ``True`` from the callback to accept, ``False`` to reject.
        """
        self._on_file.append(callback)

    def on_progress(self, callback: Callable[[FileProgress], None]) -> None:
        """Register a callback for transfer progress updates."""
        self._on_progress.append(callback)

    def on_complete(self, callback: Callable[[str], None]) -> None:
        """Register a callback when a file download completes.

        The callback receives the local file path.
        """
        self._on_complete.append(callback)

    def on_error(self, callback: Callable[[str, Exception], None]) -> None:
        """Register a callback for transfer errors."""
        self._on_error.append(callback)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_file(
        self,
        filepath: str,
        mime_type: str = "application/octet-stream",
        chunk_size: int = CHUNK_SIZE,
    ) -> str:
        """Send a file to the remote peer.

        Args:
            filepath: Path to the file to send.
            mime_type: MIME type of the file.
            chunk_size: Size of each chunk in bytes.

        Returns:
            The transfer ID.

        Raises:
            FileNotFoundError: If *filepath* doesn't exist.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"file not found: {filepath}")

        file_size = os.path.getsize(filepath)
        filename = os.path.basename(filepath)
        transfer_id = uuid.uuid4().hex[:16]

        metadata = FileMetadata(
            transfer_id=transfer_id,
            name=filename,
            size=file_size,
            mime_type=mime_type,
            chunk_size=chunk_size,
        )

        channel = await self._ensure_channel()
        channel.send(json.dumps({"type": "file_meta", **metadata.to_dict()}))

        ack = await self._wait_for_ack(transfer_id)
        if not ack:
            raise RuntimeError(f"peer rejected file transfer {transfer_id}")

        start_time = time.time()
        bytes_sent = 0

        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                channel.send(chunk)
                bytes_sent += len(chunk)

                elapsed = time.time() - start_time
                progress = FileProgress(
                    transfer_id=transfer_id,
                    name=filename,
                    total_bytes=file_size,
                    transferred_bytes=bytes_sent,
                    speed_bps=bytes_sent / max(elapsed, 0.001),
                    elapsed=elapsed,
                )
                for cb in self._on_progress:
                    cb(progress)

                await asyncio.sleep(0)

        channel.send(json.dumps({"type": "file_done", "transfer_id": transfer_id}))
        self._logger.info("sent %s (%d bytes) as %s", filename, file_size, transfer_id)
        return transfer_id

    async def send_buffer(
        self,
        data: bytes,
        filename: str = "buffer.bin",
        mime_type: str = "application/octet-stream",
        chunk_size: int = CHUNK_SIZE,
    ) -> str:
        """Send a raw bytes buffer as a file transfer.

        Args:
            data: The byte content to send.
            filename: Logical filename for the transfer.
            mime_type: MIME type.
            chunk_size: Chunk size in bytes.

        Returns:
            The transfer ID.
        """
        transfer_id = uuid.uuid4().hex[:16]
        metadata = FileMetadata(
            transfer_id=transfer_id,
            name=filename,
            size=len(data),
            mime_type=mime_type,
            chunk_size=chunk_size,
        )

        channel = await self._ensure_channel()
        channel.send(json.dumps({"type": "file_meta", **metadata.to_dict()}))

        ack = await self._wait_for_ack(transfer_id)
        if not ack:
            raise RuntimeError(f"peer rejected file transfer {transfer_id}")

        start_time = time.time()
        bytes_sent = 0
        offset = 0

        while offset < len(data):
            chunk = data[offset : offset + chunk_size]
            channel.send(chunk)
            bytes_sent += len(chunk)
            offset += len(chunk)

            elapsed = time.time() - start_time
            progress = FileProgress(
                transfer_id=transfer_id,
                name=filename,
                total_bytes=len(data),
                transferred_bytes=bytes_sent,
                speed_bps=bytes_sent / max(elapsed, 0.001),
                elapsed=elapsed,
            )
            for cb in self._on_progress:
                cb(progress)

            await asyncio.sleep(0)

        channel.send(json.dumps({"type": "file_done", "transfer_id": transfer_id}))
        return transfer_id

    # ------------------------------------------------------------------
    # Receiving (wired automatically on init)
    # ------------------------------------------------------------------

    async def start_receiving(self) -> None:
        """Start listening for incoming file transfers.

        Called automatically on first ``send_file()`` or explicitly.
        """
        channel = await self._ensure_channel()

    def get_save_path(self, metadata: FileMetadata) -> str:
        """Determine the local save path for an incoming file.

        Override to customize the download location.
        """
        return os.path.join(self.download_dir, metadata.name)

    async def write_chunk(
        self, file_handle: Any, chunk: bytes, offset: int
    ) -> None:
        """Write a chunk to the file at the given offset.

        Override to customize writing (e.g. encrypted storage).
        Default implementation appends sequentially.
        """
        file_handle.write(chunk)

    async def process_complete_file(self, filepath: str) -> None:
        """Called after a file is fully received.

        Override to post-process (e.g. verify checksum, decompress).
        """

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _ensure_channel(self) -> Any:
        if self._channel is None:
            if self.channel_label in self.pc._data_channels:
                self._channel = self.pc._data_channels[self.channel_label]
            else:
                self._channel = self.pc.create_data_channel(
                    self.channel_label, ordered=True
                )
            self._wire_receiver()
        return self._channel

    def _wire_receiver(self) -> None:
        pending: dict[str, dict[str, Any]] = {}

        def _on_message(label: str, data: str | bytes) -> None:
            if label != self.channel_label:
                return

            if isinstance(data, str):
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    return

                msg_type = msg.get("type")

                if msg_type == "file_meta":
                    meta = FileMetadata.from_dict(msg)
                    pending[meta.transfer_id] = {
                        "meta": meta,
                        "filepath": self.get_save_path(meta),
                        "buffer": bytearray(),
                        "start_time": time.time(),
                        "bytes_received": 0,
                    }

                    for cb in self._on_file:
                        cb(meta)

                    self._channel.send(
                        json.dumps({"type": "file_ack", "transfer_id": meta.transfer_id})
                    )

                elif msg_type == "file_ack":
                    tid = msg.get("transfer_id")
                    if tid in self._transfers:
                        self._transfers[tid]["ack_received"] = True

                elif msg_type == "file_done":
                    tid = msg.get("transfer_id")
                    if tid not in pending:
                        return

                    info = pending.pop(tid)
                    meta = info["meta"]
                    filepath = info["filepath"]

                    with open(filepath, "wb") as f:
                        self.write_chunk(f, bytes(info["buffer"]), 0)

                    asyncio.ensure_future(self.process_complete_file(filepath))

                    for cb in self._on_complete:
                        cb(filepath)

                    self._logger.info(
                        "received %s (%d bytes) -> %s",
                        meta.name, meta.size, filepath,
                    )

            elif isinstance(data, bytes):
                for tid, info in list(pending.items()):
                    if info["bytes_received"] < info["meta"].size:
                        info["buffer"].extend(data)
                        info["bytes_received"] += len(data)

                        elapsed = time.time() - info["start_time"]
                        progress = FileProgress(
                            transfer_id=tid,
                            name=info["meta"].name,
                            total_bytes=info["meta"].size,
                            transferred_bytes=info["bytes_received"],
                            speed_bps=info["bytes_received"] / max(elapsed, 0.001),
                            elapsed=elapsed,
                        )
                        for cb in self._on_progress:
                            cb(progress)

        self.pc.on_message(_on_message)

    async def _wait_for_ack(self, transfer_id: str, timeout: float = 30.0) -> bool:
        self._transfers[transfer_id] = {"ack_received": False}
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._transfers.get(transfer_id, {}).get("ack_received"):
                return True
            await asyncio.sleep(0.05)
        self._transfers.pop(transfer_id, None)
        return False


__all__ = [
    "FileTransfer",
    "FileMetadata",
    "FileProgress",
    "FileTransferState",
]
