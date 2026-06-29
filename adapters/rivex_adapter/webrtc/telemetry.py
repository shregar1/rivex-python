"""
Telemetry export for WebRTC connection stats.

Provides:
- ``TelemetryExporter`` — export connection stats to various backends
- ``JsonExporter`` — export to JSON files
- ``CsvExporter`` — export to CSV files
- ``LogExporter`` — export via Python logging
- ``CallbackExporter`` — export via custom callback
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, WebRTCConfig, logger


class TelemetryExporter:
    """Export WebRTC connection telemetry to multiple backends.

    Collects periodic stats from peer connections and forwards
    them to registered exporters.

    Usage::

        exporter = TelemetryExporter(interval=5.0)

        # Register backends
        exporter.add_backend(JsonExporter("/var/log/webrtc/"))
        exporter.add_backend(LogExporter())

        # Monitor a peer connection
        exporter.monitor(pc)

        # Start exporting
        await exporter.start()

    Extensibility:
        Subclass ``TelemetryExporter.Backend`` and implement
        ``write(snapshot)`` to export to custom backends.
    """

    class Backend:
        """Base class for telemetry backends.

        Implement ``open()``, ``write()``, and ``close()``.
        """

        async def open(self) -> None:
            """Open the backend for writing."""

        async def write(self, snapshot: dict[str, Any]) -> None:
            """Write a telemetry snapshot."""
            raise NotImplementedError

        async def close(self) -> None:
            """Close the backend."""

    def __init__(
        self,
        interval: float = 5.0,
        max_history: int = 0,
    ):
        self.interval = interval
        self.max_history = max_history
        self._backends: list[TelemetryExporter.Backend] = []
        self._monitored: dict[str, WebRTCPeerConnection] = {}
        self._history: list[dict[str, Any]] = []
        self._task: asyncio.Task[None] | None = None
        self._on_snapshot: list[Callable[[dict[str, Any]], None]] = []
        self._logger = logger.getChild("telemetry")

    def on_snapshot(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Called with each telemetry snapshot."""
        self._on_snapshot.append(callback)

    def add_backend(self, backend: Backend) -> None:
        """Register a telemetry backend."""
        self._backends.append(backend)

    def remove_backend(self, backend: Backend) -> None:
        """Unregister a telemetry backend."""
        self._backends.remove(backend)

    def monitor(self, pc: WebRTCPeerConnection) -> None:
        """Start monitoring a peer connection."""
        self._monitored[pc.peer_id] = pc

    def unmonitor(self, peer_id: str) -> None:
        """Stop monitoring a peer connection."""
        self._monitored.pop(peer_id, None)

    def get_history(
        self,
        peer_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get telemetry history, optionally filtered by peer."""
        snapshots = self._history
        if peer_id is not None:
            snapshots = [s for s in snapshots if s.get("peer_id") == peer_id]
        return snapshots[-limit:]

    async def start(self) -> None:
        """Start the telemetry collection loop."""
        for backend in self._backends:
            await backend.open()
        self._task = asyncio.ensure_future(self._collect_loop())

    async def stop(self) -> None:
        """Stop telemetry collection."""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        for backend in self._backends:
            await backend.close()

    async def _collect_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.interval)
                for pid, pc in list(self._monitored.items()):
                    try:
                        stats = await pc.get_stats()
                        snapshot = {
                            "timestamp": time.time(),
                            "peer_id": pid,
                            "connection_state": pc.connection_state,
                            "ice_state": pc.ice_connection_state,
                            **stats,
                        }

                        self._history.append(snapshot)
                        if self.max_history > 0:
                            self._history = self._history[-self.max_history:]

                        for backend in self._backends:
                            await backend.write(snapshot)

                        for cb in self._on_snapshot:
                            cb(snapshot)

                    except Exception as e:
                        self._logger.debug(
                            "failed to collect telemetry for %s: %s", pid, e
                        )
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    @property
    def total_snapshots(self) -> int:
        """Total number of snapshots collected."""
        return len(self._history)

    @property
    def active_peers(self) -> int:
        """Number of currently monitored peers."""
        return len(self._monitored)


# ---------------------------------------------------------------------------
# Built-in backends
# ---------------------------------------------------------------------------


class JsonExporter(TelemetryExporter.Backend):
    """Export telemetry to JSON files (one file per snapshot).

    Files are named ``webrtc_telemetry_YYYYMMDD_HHMMSS.json``.

    Usage::

        exporter.add_backend(JsonExporter("/var/log/webrtc/", rotate_hours=24))
    """

    def __init__(self, directory: str = "/tmp/webrtc-telemetry", rotate_hours: int = 0):
        self.directory = directory
        self.rotate_hours = rotate_hours
        self._current_file: Any = None
        self._current_path: str = ""
        self._last_rotate = time.time()

    async def open(self) -> None:
        os.makedirs(self.directory, exist_ok=True)
        self._rotate_file()

    async def write(self, snapshot: dict[str, Any]) -> None:
        if self._rotate_hours and (time.time() - self._last_rotate) > self.rotate_hours * 3600:
            if self._current_file is not None:
                self._current_file.close()
            self._rotate_file()

        if self._current_file is not None:
            self._current_file.write(json.dumps(snapshot, default=str) + "\n")
            self._current_file.flush()

    async def close(self) -> None:
        if self._current_file is not None:
            self._current_file.close()
            self._current_file = None

    def _rotate_file(self) -> None:
        ts = time.strftime("%Y%m%d_%H%M%S")
        self._current_path = os.path.join(self.directory, f"webrtc_telemetry_{ts}.jsonl")
        self._current_file = open(self._current_path, "a")
        self._last_rotate = time.time()


class CsvExporter(TelemetryExporter.Backend):
    """Export telemetry to CSV files.

    Writes a header row with field names and one row per snapshot.
    Fields are extracted from the snapshot dict keys.

    Usage::

        exporter.add_backend(CsvExporter("/var/log/webrtc/stats.csv"))
    """

    def __init__(self, filepath: str = "/tmp/webrtc-telemetry.csv"):
        self.filepath = filepath
        self._file: Any = None
        self._writer: Any = None
        self._fields: list[str] = []
        self._header_written = False

    async def open(self) -> None:
        os.makedirs(os.path.dirname(self.filepath) or ".", exist_ok=True)
        self._file = open(self.filepath, "a", newline="")
        self._writer = csv.writer(self._file)

    async def write(self, snapshot: dict[str, Any]) -> None:
        flat = self._flatten(snapshot)

        if not self._header_written:
            self._fields = sorted(flat.keys())
            self._writer.writerow(self._fields)
            self._header_written = True

        row = [flat.get(f, "") for f in self._fields]
        self._writer.writerow(row)
        self._file.flush()

    async def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def _flatten(self, d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in d.items():
            full_key = f"{prefix}{key}"
            if isinstance(value, dict):
                result.update(self._flatten(value, f"{full_key}_"))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        result.update(self._flatten(item, f"{full_key}_{i}_"))
                    else:
                        result[f"{full_key}_{i}"] = item
            else:
                result[full_key] = value
        return result


class LogExporter(TelemetryExporter.Backend):
    """Export telemetry via Python logging.

    Each snapshot is written at INFO level with a structured format.

    Usage::

        exporter.add_backend(LogExporter())
    """

    def __init__(self, logger_name: str = "rivex.webrtc.telemetry"):
        self._logger = logging.getLogger(logger_name)

    async def write(self, snapshot: dict[str, Any]) -> None:
        self._logger.info(
            "telemetry: peer=%s state=%s ice=%s rtt=%.1fms loss=%.1f%%",
            snapshot.get("peer_id", "?"),
            snapshot.get("connection_state", "?"),
            snapshot.get("ice_state", "?"),
            snapshot.get("rtt_ms", 0),
            snapshot.get("packet_loss_pct", 0),
        )


class CallbackExporter(TelemetryExporter.Backend):
    """Export telemetry via a custom async callback.

    Usage::

        async def send_to_api(snapshot):
            await httpx.post("https://api.example.com/webrtc/stats", json=snapshot)

        exporter.add_backend(CallbackExporter(send_to_api))
    """

    def __init__(self, callback: Callable[[dict[str, Any]], None]):
        self._callback = callback

    async def write(self, snapshot: dict[str, Any]) -> None:
        await self._callback(snapshot)


__all__ = [
    "TelemetryExporter",
    "JsonExporter",
    "CsvExporter",
    "LogExporter",
    "CallbackExporter",
]
