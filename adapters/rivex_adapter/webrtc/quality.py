"""
Connection quality monitoring for WebRTC.

Provides:
- ``ConnectionQualityMonitor`` — periodic stats collection and quality scoring

Plug into any ``WebRTCPeerConnection`` via ``pc.on_stats()``.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger


class ConnectionQualityMonitor:
    """Monitors WebRTC connection quality and reports metrics.

    Attach to a ``WebRTCPeerConnection``::

        monitor = ConnectionQualityMonitor()
        pc.on_stats(monitor.on_stats)
        monitor.on_quality_change(lambda metrics: print(metrics))

    Produces quality metrics including:
    - Round-trip time (RTT)
    - Jitter
    - Packet loss percentage
    - Available bitrate
    - Quality score (0.0 – 1.0)

    Extensibility:
        Subclass and override ``compute_quality_score()`` to implement
        custom quality scoring logic. Override ``process_stats()`` to
        add custom aggregation.
    """

    LOW_BITRATE_THRESHOLD = 100_000
    HIGH_RTT_THRESHOLD = 0.3
    HIGH_JITTER_THRESHOLD = 0.05
    HIGH_LOSS_THRESHOLD = 0.05
    SAMPLE_WINDOW = 10

    def __init__(self):
        self._rtt_samples: list[float] = []
        self._jitter_samples: list[float] = []
        self._loss_samples: list[float] = []
        self._bitrate_samples: list[float] = []
        self._quality_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._last_report: dict[str, Any] = {}
        self._logger = logger.getChild("quality")

    def on_quality_change(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a callback for quality metric updates.

        The callback receives a dict with current metrics.
        """
        self._quality_callbacks.append(callback)

    def on_stats(self, stats: dict[str, Any]) -> None:
        """Process a stats snapshot from ``WebRTCPeerConnection.get_stats()``.

        This method is designed to be passed directly to
        ``WebRTCPeerConnection.on_stats()``.
        """
        metrics = self.process_stats(stats)
        if metrics is not None:
            self._last_report = metrics
            for cb in self._quality_callbacks:
                cb(metrics)

    def process_stats(
        self, stats: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Process raw stats dict and return quality metrics.

        Override to customize aggregation logic.
        """
        pairs = stats.get("ice_candidate_pairs", [])
        active_pairs = [p for p in pairs if p.get("nominated")]

        rtt: float | None = None
        bitrate: float | None = None
        for pair in active_pairs:
            if "current_rtt" in pair:
                rtt = pair["current_rtt"]
            if "available_outgoing_bitrate" in pair:
                bitrate = pair["available_outgoing_bitrate"]

        inbound = stats.get("inbound_rtp", [])
        total_packets = 0
        total_lost = 0
        jitters: list[float] = []
        for stream in inbound:
            total_packets += stream.get("packets_received", 0)
            total_lost += stream.get("packets_lost", 0)
            if "jitter" in stream:
                jitters.append(stream["jitter"])

        loss_ratio = total_lost / max(total_packets, 1)
        avg_jitter = sum(jitters) / max(len(jitters), 1) if jitters else 0.0

        self._rtt_samples.append(rtt or 0.0)
        self._jitter_samples.append(avg_jitter)
        self._loss_samples.append(loss_ratio)
        if bitrate is not None:
            self._bitrate_samples.append(bitrate)

        self._rtt_samples = self._rtt_samples[-self.SAMPLE_WINDOW:]
        self._jitter_samples = self._jitter_samples[-self.SAMPLE_WINDOW:]
        self._loss_samples = self._loss_samples[-self.SAMPLE_WINDOW:]
        self._bitrate_samples = self._bitrate_samples[-self.SAMPLE_WINDOW:]

        avg_rtt = sum(self._rtt_samples) / max(len(self._rtt_samples), 1)
        avg_loss = sum(self._loss_samples) / max(len(self._loss_samples), 1)
        avg_bitrate = sum(self._bitrate_samples) / max(len(self._bitrate_samples), 1) if self._bitrate_samples else 0.0

        score = self.compute_quality_score(
            rtt=avg_rtt,
            jitter=avg_jitter,
            loss=avg_loss,
            bitrate=avg_bitrate,
        )

        return {
            "timestamp": time.time(),
            "rtt_ms": round(avg_rtt * 1000, 2),
            "jitter_ms": round(avg_jitter * 1000, 2),
            "packet_loss_pct": round(avg_loss * 100, 2),
            "available_bitrate_bps": round(avg_bitrate),
            "quality_score": round(score, 3),
            "total_packets_received": total_packets,
            "total_packets_lost": total_lost,
        }

    def compute_quality_score(
        self,
        rtt: float,
        jitter: float,
        loss: float,
        bitrate: float,
    ) -> float:
        """Compute a quality score from 0.0 (worst) to 1.0 (best).

        Override to implement custom scoring logic. The default
        scoring penalizes high RTT, jitter, packet loss, and
        low bitrate.
        """
        rtt_score = max(0.0, 1.0 - rtt / self.HIGH_RTT_THRESHOLD)
        jitter_score = max(0.0, 1.0 - jitter / self.HIGH_JITTER_THRESHOLD)
        loss_score = max(0.0, 1.0 - loss / self.HIGH_LOSS_THRESHOLD)
        bitrate_score = min(1.0, bitrate / self.LOW_BITRATE_THRESHOLD) if bitrate > 0 else 0.5

        return 0.25 * rtt_score + 0.25 * jitter_score + 0.25 * loss_score + 0.25 * bitrate_score

    @property
    def last_report(self) -> dict[str, Any]:
        """Most recently computed quality metrics."""
        return self._last_report


__all__ = [
    "ConnectionQualityMonitor",
]
