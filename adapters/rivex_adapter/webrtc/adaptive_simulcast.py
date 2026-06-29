"""
Adaptive simulcast coordinator — bridges bandwidth estimation,
connection quality monitoring, and simulcast management to
automatically switch between simulcast tiers in real-time.

``AdaptiveSimulcast`` — reads from ``BandwidthEstimator`` and
``ConnectionQualityMonitor``, then calls ``SimulcastManager``
to enable/disable layers.

Usage::

    coord = AdaptiveSimulcast(
        bandwidth_estimator=estimator,
        quality_monitor=quality_monitor,
        simulcast_manager=simulcast_mgr,
    )

    coord.on_tier_change(lambda peer_id, new_tier: ...)
    await coord.start(interval=1.0)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from rivex_adapter.webrtc.bandwidth import BandwidthEstimator
from rivex_adapter.webrtc.codecs import SimulcastManager
from rivex_adapter.webrtc.quality import ConnectionQualityMonitor
from rivex_adapter.webrtc.core import logger


class SimulcastTier(str, Enum):
    """Simulcast encoding tiers."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    OFF = "off"


@dataclass
class TierDecision:
    """Decision about which tiers should be active."""

    enabled_tiers: list[SimulcastTier]
    reason: str = ""
    estimated_bitrate_kbps: float = 0.0
    quality_score: float = 0.0
    rtt_ms: float = 0.0
    loss_pct: float = 0.0


class AdaptiveSimulcast:
    """Automatically selects simulcast tiers based on network conditions.

    Decision logic:
        - Bandwidth > 2 Mbps → HIGH + MEDIUM + LOW
        - Bandwidth > 800 Kbps → MEDIUM + LOW
        - Bandwidth > 300 Kbps → LOW
        - Bandwidth <= 300 Kbps → OFF

    Quality override:
        - quality < 2 (poor) → drop to LOW
        - quality >= 3 (good) → allow HIGH
        - RTT > 500 ms → cap at MEDIUM
        - loss > 5% → drop to LOW
    """

    def __init__(
        self,
        bandwidth_estimator: BandwidthEstimator,
        quality_monitor: ConnectionQualityMonitor,
        simulcast_manager: SimulcastManager,
    ):
        self._bwe = bandwidth_estimator
        self._quality = quality_monitor
        self._simulcast = simulcast_manager

        self._tier_handlers: list[Callable[[str, list[SimulcastTier]], None]] = []
        self._per_peer_tiers: dict[str, list[SimulcastTier]] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        self._logger = logger.getChild("adaptive_simulcast")

    def on_tier_change(
        self, handler: Callable[[str, list[SimulcastTier]], None],
    ) -> None:
        """Called when a peer's active tiers change."""
        self._tier_handlers.append(handler)

    async def start(self, interval: float = 1.0) -> None:
        """Start the adaptation loop."""
        self._running = True
        self._task = asyncio.ensure_future(self._loop(interval))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self, interval: float) -> None:
        while self._running:
            try:
                await self._evaluate_all()
            except Exception:
                self._logger.exception("evaluation error")
            await asyncio.sleep(interval)

    async def evaluate(self, peer_id: str) -> TierDecision:
        """Evaluate and apply tier decision for a single peer."""
        decision = self._decide(peer_id)
        old_tiers = self._per_peer_tiers.get(peer_id, [])
        if set(decision.enabled_tiers) != set(old_tiers):
            self._per_peer_tiers[peer_id] = decision.enabled_tiers
            self._apply(peer_id, decision)
            for handler in self._tier_handlers:
                try:
                    handler(peer_id, decision.enabled_tiers)
                except Exception:
                    self._logger.exception("tier handler error")
        return decision

    async def _evaluate_all(self) -> None:
        for peer_id in list(self._per_peer_tiers.keys()):
            await self.evaluate(peer_id)

    def _decide(self, peer_id: str) -> TierDecision:
        bps = getattr(self._bwe, "_last_estimate", 0) or self._bwe.current_estimate
        bitrate_kbps = bps / 1000.0

        quality = 3
        rtt = 0.0
        loss = 0.0
        try:
            score = getattr(self._quality, "get_score", None)
            if score:
                quality = score(peer_id) or 3
        except Exception:
            pass
        try:
            loss = getattr(self._quality, "avg_loss", None)
            if loss is None:
                stats = getattr(self._quality, "get_stats", None)
                if stats:
                    s = stats(peer_id)
                    loss = getattr(s, "avg_loss", None)
        except Exception:
            pass
        try:
            rtt = getattr(self._quality, "avg_rtt", None)
            if rtt is None:
                stats = getattr(self._quality, "get_stats", None)
                if stats:
                    s = stats(peer_id)
                    rtt = getattr(s, "avg_rtt", None)
        except Exception:
            pass
        loss = loss or 0.0
        rtt = rtt or 0.0

        tiers = self._choose_tiers(bitrate_kbps, quality, rtt, loss)
        reason_parts = []
        if bitrate_kbps > 2000:
            reason_parts.append("high bandwidth")
        elif bitrate_kbps > 800:
            reason_parts.append("medium bandwidth")
        elif bitrate_kbps > 300:
            reason_parts.append("low bandwidth")
        else:
            reason_parts.append("insufficient bandwidth")
        if quality < 2:
            reason_parts.append("poor quality")
        if rtt > 500:
            reason_parts.append("high latency")
        if loss > 5:
            reason_parts.append("packet loss")

        return TierDecision(
            enabled_tiers=tiers,
            reason=", ".join(reason_parts),
            estimated_bitrate_kbps=bitrate_kbps,
            quality_score=quality,
            rtt_ms=rtt,
            loss_pct=loss,
        )

    def _choose_tiers(
        self, bitrate_kbps: float, quality: float, rtt: float, loss: float,
    ) -> list[SimulcastTier]:
        if loss > 5:
            return [SimulcastTier.OFF]
        if loss > 3:
            return [SimulcastTier.LOW]
        if rtt > 500:
            return [SimulcastTier.LOW]
        if quality < 2:
            return [SimulcastTier.LOW]

        if bitrate_kbps > 2000 and quality >= 3:
            return [SimulcastTier.HIGH, SimulcastTier.MEDIUM, SimulcastTier.LOW]
        if bitrate_kbps > 800:
            return [SimulcastTier.MEDIUM, SimulcastTier.LOW]
        if bitrate_kbps > 300:
            return [SimulcastTier.LOW]

        return [SimulcastTier.OFF]

    def _apply(self, peer_id: str, decision: TierDecision) -> None:
        tier_map = {
            SimulcastTier.OFF: [],
            SimulcastTier.LOW: ["low"],
            SimulcastTier.MEDIUM: ["low", "medium"],
            SimulcastTier.HIGH: ["low", "medium", "high"],
        }
        active = []
        for t in decision.enabled_tiers:
            active.extend(tier_map.get(t, []))
        active = list(dict.fromkeys(active))

        try:
            self._simulcast.set_active_layers(peer_id, active)
        except Exception as e:
            self._logger.warning("apply failed for %s: %s", peer_id, e)


__all__ = [
    "AdaptiveSimulcast",
    "SimulcastTier",
    "TierDecision",
]
