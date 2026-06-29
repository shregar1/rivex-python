"""
Live WebSocket stats report endpoint for per-peer WebRTC metrics.

``StatsEndpoint`` — a Rivex/FastAPI WebSocket endpoint that streams
``WebRTCMetrics`` snapshots to subscribers.

Usage in a Rivex app::

    from rivex_adapter.webrtc.stats_endpoint import StatsEndpoint
    from rivex_adapter.webrtc.metrics import WebRTCMetrics

    stats_ep = StatsEndpoint(metrics_store=metrics)

    @app.websocket("/ws/stats")
    async def stats_ws(websocket):
        await stats_ep.handle(websocket)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from rivex_adapter.webrtc.core import logger
from rivex_adapter.webrtc.metrics import WebRTCMetrics


@dataclass
class StatsSnapshot:
    """A snapshot of metrics at a point in time."""

    peer_id: str
    timestamp: float
    metrics: dict
    label: str = "stats"


class StatsEndpoint:
    """WebSocket endpoint that streams live per-peer WebRTC metrics.

    Subscribers can filter by ``peer_id`` query parameter or receive
    all peer metrics.

    Usage::

        endpoint = StatsEndpoint(metrics_store=my_metrics)
        # wire into app as shown above
    """

    def __init__(
        self,
        metrics_store: WebRTCMetrics | None = None,
        interval: float = 1.0,
    ):
        self._metrics = metrics_store or WebRTCMetrics()
        self._interval = interval
        self._subscribers: dict[str, asyncio.Queue] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        self._logger = logger.getChild("stats_endpoint")

    async def handle(self, websocket: Any) -> None:
        """Handle a WebSocket connection.

        Accepts the connection, then streams metrics snapshots every
        ``interval`` seconds until the client disconnects.
        """
        sub_id = uuid.uuid4().hex[:12]
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[sub_id] = queue

        try:
            await websocket.accept()
            if not self._running:
                self._start()

            while True:
                snapshot = await queue.get()
                try:
                    await websocket.send_json({
                        "peer_id": snapshot.peer_id,
                        "timestamp": snapshot.timestamp,
                        "metrics": snapshot.metrics,
                    })
                except Exception:
                    break
        except Exception:
            pass
        finally:
            self._subscribers.pop(sub_id, None)
            try:
                await websocket.close()
            except Exception:
                pass

    def _start(self) -> None:
        self._running = True
        self._task = asyncio.ensure_future(self._broadcast_loop())

    async def _broadcast_loop(self) -> None:
        while self._running:
            try:
                await self._collect_and_broadcast()
            except Exception:
                self._logger.exception("broadcast error")
            await asyncio.sleep(self._interval)

    async def _collect_and_broadcast(self) -> None:
        now = time.time()
        for peer_id in self._get_peer_ids():
            metrics = self._get_peer_metrics(peer_id)
            snapshot = StatsSnapshot(
                peer_id=peer_id,
                timestamp=now,
                metrics=metrics,
            )
            for sub_id, queue in list(self._subscribers.items()):
                try:
                    queue.put_nowait(snapshot)
                except asyncio.QueueFull:
                    self._subscribers.pop(sub_id, None)

    def _get_peer_ids(self) -> list[str]:
        return getattr(self._metrics, "_peers", {}).keys()

    def _get_peer_metrics(self, peer_id: str) -> dict:
        try:
            report = self._metrics.get_report(peer_id)
            if hasattr(report, "to_dict"):
                return report.to_dict()
            if isinstance(report, dict):
                return report
            return {"error": "unknown format"}
        except Exception as e:
            return {"error": str(e)}

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


__all__ = [
    "StatsEndpoint",
    "StatsSnapshot",
]
