"""
Load testing utilities for WebRTC conferences.

``SimulatedPeer`` — a lightweight virtual peer that connects to a
signalling server, creates a ``WebRTCPeerConnection``, and optionally
sends/receives synthetic audio/video.

``LoadTest`` — orchestrates *N* virtual peers, joins them to a room,
collects metrics (connect time, bitrate, packet loss), and produces
a report.

Usage::

    load = LoadTest(
        signaling_url="ws://localhost:8000/ws",
        room="test-room",
        num_peers=50,
        ramp_up=10,           # add 10 peers every 5 seconds
    )
    report = await load.run(duration=60)
    print(report.summary())
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import statistics
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger
from rivex_adapter.webrtc.conference import ConferenceBridge


# ---------------------------------------------------------------------------
# Synthetic audio/video
# ---------------------------------------------------------------------------


class _SilenceTrack:
    """Synthetic silent audio track (16‑bit mono 48 kHz silence)."""

    kind = "audio"
    id: str = ""

    def __init__(self, track_id: str = ""):
        self.id = track_id or f"audio-synth-{uuid.uuid4().hex[:8]}"

    async def recv(self) -> Any:
        await asyncio.sleep(0.02)  # 20 ms = 50 fps
        return None  # placeholder — real impl would return silence frame


class _ColorBarsTrack:
    """Synthetic video track (solid colour frames)."""

    kind = "video"
    id: str = ""

    def __init__(self, track_id: str = "", fps: int = 15):
        self.id = track_id or f"video-synth-{uuid.uuid4().hex[:8]}"
        self._fps = fps

    async def recv(self) -> Any:
        await asyncio.sleep(1.0 / self._fps)
        return None  # placeholder


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@dataclass
class PeerMetrics:
    """Metrics collected for a single simulated peer."""

    peer_id: str
    connected: bool = False
    connect_time_ms: float = 0.0
    disconnect_time_ms: float = 0.0
    total_bytes_sent: int = 0
    total_bytes_received: int = 0
    packets_sent: int = 0
    packets_lost: int = 0
    avg_rtt_ms: float = 0.0
    errors: list[str] = field(default_factory=list)
    ice_candidates: int = 0
    ice_pairs: int = 0


@dataclass
class LoadTestReport:
    """Aggregated load test report."""

    num_peers: int
    duration: float
    room: str
    signaling_url: str
    success_count: int
    failure_count: int
    connect_time_stats: dict[str, float] = field(default_factory=dict)
    rtt_stats: dict[str, float] = field(default_factory=dict)
    loss_percent: float = 0.0
    throughput_kbps: float = 0.0
    per_peer: list[PeerMetrics] = field(default_factory=list)

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = [
            "═" * 50,
            "Load Test Report",
            "═" * 50,
            f"  Room:            {self.room}",
            f"  Signaling:       {self.signaling_url}",
            f"  Peers:           {self.num_peers}  "
            f"(✓ {self.success_count}  ✗ {self.failure_count})",
            f"  Duration:        {self.duration:.1f}s",
            "",
            "  Connection time:",
            f"    min    {self.connect_time_stats.get('min', 0):.1f} ms",
            f"    avg    {self.connect_time_stats.get('mean', 0):.1f} ms",
            f"    p95    {self.connect_time_stats.get('p95', 0):.1f} ms",
            f"    max    {self.connect_time_stats.get('max', 0):.1f} ms",
            "",
            "  RTT:",
            f"    min    {self.rtt_stats.get('min', 0):.1f} ms",
            f"    avg    {self.rtt_stats.get('mean', 0):.1f} ms",
            f"    max    {self.rtt_stats.get('max', 0):.1f} ms",
            "",
            f"  Packet loss:     {self.loss_percent:.2f}%",
            f"  Throughput:      {self.throughput_kbps:.1f} Kbps",
            "═" * 50,
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Simulated Peer
# ---------------------------------------------------------------------------


class SimulatedPeer:
    """A virtual peer for load testing.

    Usage::

        peer = SimulatedPeer(
            bridge=conference_bridge,
            peer_id="load-001",
        )
        await peer.connect()
        # ... do stuff ...
        metrics = await peer.disconnect()
    """

    def __init__(
        self,
        bridge: ConferenceBridge,
        peer_id: str | None = None,
        on_metrics: Callable[[PeerMetrics], None] | None = None,
        send_audio: bool = False,
        send_video: bool = False,
    ):
        self.bridge = bridge
        self.room = bridge.room
        self.peer_id = peer_id or f"load-{uuid.uuid4().hex[:8]}"
        self._on_metrics = on_metrics
        self._send_audio = send_audio
        self._send_video = send_video

        self.pc: WebRTCPeerConnection | None = None

        self._start_time: float = 0.0
        self._connect_time: float = 0.0
        self._metrics = PeerMetrics(peer_id=self.peer_id)
        self._logger = logger.getChild(f"load-{self.peer_id}")

    async def connect(self) -> WebRTCPeerConnection:
        """Connect to the room via ConferenceBridge.

        Returns:
            The underlying ``WebRTCPeerConnection``.
        """
        self._start_time = time.monotonic()

        self.pc = await self.bridge.add_peer(self.peer_id)

        if self._send_audio:
            track = _SilenceTrack()
            self.pc.add_track(track)

        if self._send_video:
            track = _ColorBarsTrack()
            self.pc.add_track(track)

        self._connect_time = time.monotonic() - self._start_time
        self._metrics.connected = True
        self._metrics.connect_time_ms = self._connect_time * 1000.0

        self._logger.info(
            "Connected in %.0f ms", self._metrics.connect_time_ms
        )

        return self.pc

    async def disconnect(self) -> PeerMetrics:
        """Disconnect and collect metrics.

        Returns:
            Collected ``PeerMetrics``.
        """
        self._metrics.disconnect_time_ms = (
            time.monotonic() - self._start_time
        ) * 1000.0

        try:
            await self.bridge.remove_peer(self.peer_id)
        except Exception as e:
            self._metrics.errors.append(str(e))

        self._collect_metrics()

        if self._on_metrics:
            self._on_metrics(self._metrics)

        return self._metrics

    def _collect_metrics(self) -> None:
        if not self.pc:
            return
        pc = self.pc
        self._metrics.ice_candidates = len(pc.remote_candidates)
        self._metrics.ice_pairs = len(getattr(pc, "ice_candidate_pairs", []))

        if hasattr(pc, "_stats") and pc._stats:
            stats = pc._stats
            self._metrics.total_bytes_sent = stats.get("bytes_sent", 0)
            self._metrics.total_bytes_received = stats.get("bytes_received", 0)
            self._metrics.packets_sent = stats.get("packets_sent", 0)
            self._metrics.packets_lost = stats.get("packets_lost", 0)
            self._metrics.avg_rtt_ms = stats.get("rtt", 0.0)

    def add_error(self, msg: str) -> None:
        self._metrics.errors.append(msg)
        self._logger.warning(msg)


# ---------------------------------------------------------------------------
# Load Test Orchestrator
# ---------------------------------------------------------------------------


class LoadTest:
    """Orchestrate a load test with many virtual peers.

    Usage::

        load = LoadTest(
            signaling_url="ws://localhost:8000/ws",
            room="stress-test",
            num_peers=100,
            ramp_up=20,
            ramp_up_interval=2.0,
        )
        report = await load.run(duration=30)
    """

    def __init__(
        self,
        bridge: ConferenceBridge,
        num_peers: int = 10,
        ramp_up: int = 5,
        ramp_up_interval: float = 1.0,
        send_audio: bool = False,
        send_video: bool = False,
    ):
        self.bridge = bridge
        self.room = bridge.room
        self.num_peers = num_peers
        self.ramp_up = ramp_up
        self.ramp_up_interval = ramp_up_interval
        self.send_audio = send_audio
        self.send_video = send_video

        self._peers: list[SimulatedPeer] = []
        self._reports: list[PeerMetrics] = []
        self._logger = logger.getChild("loadtest")

    async def run(
        self,
        duration: float = 30.0,
        progress_callback: Callable[[int, int], None] = None,
    ) -> LoadTestReport:
        """Run the load test.

        Args:
            duration: How long to keep peers connected (seconds).
            progress_callback: Called with ``(connected, total)``.

        Returns:
            An aggregated ``LoadTestReport``.
        """
        start = time.monotonic()

        self._peers = []
        self._reports = []

        conductor = _LoadTestConductor(
            bridge=self.bridge,
            num_peers=self.num_peers,
            ramp_up=self.ramp_up,
            ramp_up_interval=self.ramp_up_interval,
            send_audio=self.send_audio,
            send_video=self.send_video,
            logger=self._logger,
            on_metrics=self._on_peer_metrics,
        )

        connected = await conductor.connect_all(progress_callback)
        if connected == 0:
            return LoadTestReport(
                num_peers=self.num_peers,
                duration=0.0,
                room=self.bridge.room,
                signaling_url=str(getattr(self.bridge, "_signaling_url", "")),
                success_count=0,
                failure_count=self.num_peers,
            )

        elapsed_connect = time.monotonic() - start
        await asyncio.sleep(max(0, duration - elapsed_connect))

        await conductor.disconnect_all()
        total_time = time.monotonic() - start

        report = self._aggregate(total_time, connected)
        self._logger.info(
            "\n" + report.summary()
        )
        return report

    def _on_peer_metrics(self, m: PeerMetrics) -> None:
        self._reports.append(m)

    def _aggregate(
        self, duration: float, connected: int
    ) -> LoadTestReport:
        connect_times = [m.connect_time_ms for m in self._reports if m.connected]
        rtts = [m.avg_rtt_ms for m in self._reports if m.avg_rtt_ms > 0]
        total_lost = sum(m.packets_lost for m in self._reports)
        total_sent = sum(m.packets_sent for m in self._reports)
        total_bytes = sum(
            m.total_bytes_sent + m.total_bytes_received
            for m in self._reports
        )
        failure = sum(1 for m in self._reports if not m.connected)

        def stats(vals):
            if not vals:
                return {}
            return {
                "min": min(vals),
                "mean": statistics.mean(vals),
                "median": statistics.median(vals),
                "p95": sorted(vals)[int(len(vals) * 0.95)],
                "max": max(vals),
            }

        return LoadTestReport(
            num_peers=self.num_peers,
            duration=duration,
            room=self.bridge.room,
            signaling_url=str(getattr(self.bridge, "_signaling_url", "")),
            success_count=connected - failure,
            failure_count=failure,
            connect_time_stats=stats(connect_times),
            rtt_stats=stats(rtts),
            loss_percent=(total_lost / max(total_sent, 1)) * 100,
            throughput_kbps=(total_bytes * 8 / max(duration, 0.01)) / 1000,
            per_peer=self._reports,
        )


class _LoadTestConductor:
    """Handles the peer lifecycle under the hood."""

    def __init__(self, **kwargs):
        self.bridge = kwargs["bridge"]
        self.num_peers = kwargs["num_peers"]
        self.ramp_up = kwargs["ramp_up"]
        self.ramp_up_interval = kwargs["ramp_up_interval"]
        self.send_audio = kwargs["send_audio"]
        self.send_video = kwargs["send_video"]
        self._logger = kwargs["logger"]
        self._on_metrics = kwargs["on_metrics"]
        self._peers: list[SimulatedPeer] = []
        self._errors: list[str] = []

    async def connect_all(
        self, progress_callback=None
    ) -> int:
        batch_size = max(1, self.ramp_up)
        connected = 0

        for i in range(0, self.num_peers, batch_size):
            batch = min(batch_size, self.num_peers - i)
            tasks = []
            for j in range(batch):
                peer = SimulatedPeer(
                    bridge=self.bridge,
                    peer_id=f"load-{i+j:04d}",
                    on_metrics=self._on_metrics,
                    send_audio=self.send_audio,
                    send_video=self.send_video,
                )
                self._peers.append(peer)
                tasks.append(self._connect_one(peer))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    self._errors.append(str(r))
                else:
                    connected += 1

            if progress_callback:
                progress_callback(connected, self.num_peers)
            self._logger.info(
                "Progress: %d / %d connected", connected, self.num_peers
            )

            if i + batch < self.num_peers:
                await asyncio.sleep(self.ramp_up_interval)

        return connected

    async def _connect_one(self, peer: SimulatedPeer) -> None:
        try:
            await peer.connect()
        except Exception as e:
            peer.add_error(str(e))
            raise

    async def disconnect_all(self) -> None:
        tasks = [peer.disconnect() for peer in self._peers]
        await asyncio.gather(*tasks, return_exceptions=True)


__all__ = [
    "LoadTest",
    "LoadTestReport",
    "SimulatedPeer",
    "PeerMetrics",
]
