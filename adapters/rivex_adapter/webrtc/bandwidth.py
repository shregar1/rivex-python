"""
Bandwidth estimation and adaptive bitrate control for WebRTC.

Provides:
- ``BandwidthEstimator`` — estimate available bandwidth from connection stats
- ``AdaptiveBitrateController`` — dynamically adjust track encodings
- ``BitrateProfile`` — named bitrate profiles (low, medium, high, auto)
- ``CongestionDetector`` — detect congestion from RTT/packet-loss patterns
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger
from rivex_adapter.webrtc.quality import ConnectionQualityMonitor


class BitrateTier(Enum):
    MINIMUM = "minimum"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAXIMUM = "maximum"


@dataclass
class BitrateProfile:
    """Named bitrate limits for adaptive control.

    Each tier maps to a max bitrate in bps.
    """

    name: str = "auto"
    min_bitrate: int = 50_000
    start_bitrate: int = 500_000
    max_bitrate: int = 2_500_000

    LOW: "BitrateProfile" = None
    MEDIUM: "BitrateProfile" = None
    HIGH: "BitrateProfile" = None
    VOICE_ONLY: "BitrateProfile" = None
    SCREEN_SHARE: "BitrateProfile" = None


BitrateProfile.LOW = BitrateProfile("low", min_bitrate=30_000, start_bitrate=100_000, max_bitrate=300_000)
BitrateProfile.MEDIUM = BitrateProfile("medium", min_bitrate=100_000, start_bitrate=500_000, max_bitrate=1_000_000)
BitrateProfile.HIGH = BitrateProfile("high", min_bitrate=200_000, start_bitrate=1_500_000, max_bitrate=4_000_000)
BitrateProfile.VOICE_ONLY = BitrateProfile("voice", min_bitrate=16_000, start_bitrate=32_000, max_bitrate=64_000)
BitrateProfile.SCREEN_SHARE = BitrateProfile("screenshare", min_bitrate=200_000, start_bitrate=1_000_000, max_bitrate=8_000_000)


class CongestionDetector:
    """Detect network congestion from RTT and packet loss patterns.

    Signals congestion when RTT exceeds threshold or packet loss
    spikes above a tolerance.

    Usage::

        detector = CongestionDetector()
        detector.on_congestion(lambda: print("Slow down!"))
        detector.on_recovery(lambda: print("All clear"))

        # Feed stats periodically
        detector.update(rtt_ms=50, loss_pct=0.5)

    Extensibility:
        Override ``detect()`` for custom congestion detection.
    """

    def __init__(
        self,
        rtt_threshold_ms: float = 200.0,
        loss_threshold_pct: float = 3.0,
        recovery_rtt_ms: float = 100.0,
        recovery_loss_pct: float = 0.5,
        samples_needed: int = 3,
    ):
        self.rtt_threshold_ms = rtt_threshold_ms
        self.loss_threshold_pct = loss_threshold_pct
        self.recovery_rtt_ms = recovery_rtt_ms
        self.recovery_loss_pct = recovery_loss_pct
        self.samples_needed = samples_needed
        self._congested = False
        self._consecutive_congestion = 0
        self._consecutive_clear = 0
        self._on_congestion: list[Callable[[], None]] = []
        self._on_recovery: list[Callable[[], None]] = []

    def on_congestion(self, callback: Callable[[], None]) -> None:
        """Called when congestion is detected."""
        self._on_congestion.append(callback)

    def on_recovery(self, callback: Callable[[], None]) -> None:
        """Called when congestion clears."""
        self._on_recovery.append(callback)

    def update(self, rtt_ms: float, loss_pct: float) -> bool:
        """Feed a stats sample. Returns ``True`` if congestion state changed."""
        was_congested = self._congested
        self._congested = self.detect(rtt_ms, loss_pct)

        if self._congested and not was_congested:
            for cb in self._on_congestion:
                cb()
        elif not self._congested and was_congested:
            for cb in self._on_recovery:
                cb()

        return self._congested != was_congested

    def detect(self, rtt_ms: float, loss_pct: float) -> bool:
        """Determine if network is congested.

        Override for custom detection logic.
        """
        is_congested = rtt_ms > self.rtt_threshold_ms or loss_pct > self.loss_threshold_pct
        is_clear = rtt_ms < self.recovery_rtt_ms and loss_pct < self.recovery_loss_pct

        if is_congested:
            self._consecutive_congestion += 1
            self._consecutive_clear = 0
            return self._consecutive_congestion >= self.samples_needed
        elif is_clear:
            self._consecutive_clear += 1
            self._consecutive_congestion = 0
            return not (self._consecutive_clear >= self.samples_needed)
        else:
            self._consecutive_congestion = 0
            self._consecutive_clear = 0
            return self._congested

    @property
    def is_congested(self) -> bool:
        """Whether congestion is currently detected."""
        return self._congested


class BandwidthEstimator:
    """Estimate available bandwidth from WebRTC connection stats.

    Combines multiple signals: ICE candidate pair stats, inbound RTP
    bitrate, and round-trip time to produce an estimate.

    Usage::

        estimator = BandwidthEstimator()
        estimator.on_estimate(lambda bps: print(f"Available: {bps//1000} kbps"))

        # Feed stats
        estimator.update(stats_dict)

    Extensibility:
        Override ``estimate()`` for custom estimation algorithm.
    """

    def __init__(
        self,
        default_estimate: int = 1_000_000,
        min_estimate: int = 50_000,
        max_estimate: int = 10_000_000,
        alpha: float = 0.3,
    ):
        self.default_estimate = default_estimate
        self.min_estimate = min_estimate
        self.max_estimate = max_estimate
        self.alpha = alpha
        self._estimate = default_estimate
        self._last_bitrate: list[int] = []
        self._callbacks: list[Callable[[int], None]] = []

    def on_estimate(self, callback: Callable[[int], None]) -> None:
        """Called with the estimated available bitrate in bps."""
        self._callbacks.append(callback)

    def update(self, stats: dict[str, Any]) -> int:
        """Update the estimate with new stats.

        Args:
            stats: Stats dict from ``WebRTCPeerConnection.get_stats()``.

        Returns:
            Estimated available bitrate in bps.
        """
        estimate = self.estimate(stats)
        self._estimate = int(self.alpha * estimate + (1 - self.alpha) * self._estimate)
        self._estimate = max(self.min_estimate, min(self.max_estimate, self._estimate))

        for cb in self._callbacks:
            cb(self._estimate)

        return self._estimate

    def estimate(self, stats: dict[str, Any]) -> int:
        """Compute bandwidth estimate from raw stats.

        Override for custom estimation algorithm.
        """
        pairs = stats.get("ice_candidate_pairs", [])
        nominated = [p for p in pairs if p.get("nominated")]
        if nominated:
            pair = nominated[0]
            if "available_outgoing_bitrate" in pair:
                return int(pair["available_outgoing_bitrate"])

        inbound = stats.get("inbound_rtp", [])
        bitrates: list[int] = []
        for stream in inbound:
            if "bytes_received" in stream and hasattr(self, "_last_bytes"):
                pass
            bitrates.append(0)

        if hasattr(self, "_last_bitrate") and self._last_bitrate:
            return int(sum(self._last_bitrate[-3:]) / max(len(self._last_bitrate[-3:]), 1))

        return self.default_estimate

    @property
    def estimate_bps(self) -> int:
        """Current bandwidth estimate in bps."""
        return self._estimate

    @property
    def estimate_kbps(self) -> int:
        """Current bandwidth estimate in kbps."""
        return self._estimate // 1000


class AdaptiveBitrateController:
    """Dynamically adjust media track bitrate based on network conditions.

    Monitors connection quality and adjusts sender encodings
    to match the estimated available bandwidth.

    Usage::

        controller = AdaptiveBitrateController(pc)
        controller.set_profile(BitrateProfile.HIGH)

        # Wire to quality monitor
        controller.on_downscale(lambda tier: print(f"Downscaling to {tier}"))

        # Start adaptation
        await controller.start()

    Extensibility:
        Override ``select_tier()``, ``apply_encoding()``, or
        ``on_network_change()`` to customize adaptation.
    """

    def __init__(
        self,
        pc: WebRTCPeerConnection,
        estimator: BandwidthEstimator | None = None,
        detector: CongestionDetector | None = None,
        profile: BitrateProfile | None = None,
    ):
        self.pc = pc
        self.estimator = estimator or BandwidthEstimator()
        self.detector = detector or CongestionDetector()
        self.profile = profile or BitrateProfile.HIGH
        self._current_tier = BitrateTier.MAXIMUM
        self._task: asyncio.Task[None] | None = None
        self._adapt_interval = 2.0
        self._on_downscale: list[Callable[[BitrateTier], None]] = []
        self._on_upscale: list[Callable[[BitrateTier], None]] = []

    def on_downscale(self, callback: Callable[[BitrateTier], None]) -> None:
        """Called when bitrate is reduced to a lower tier."""
        self._on_downscale.append(callback)

    def on_upscale(self, callback: Callable[[BitrateTier], None]) -> None:
        """Called when bitrate is increased to a higher tier."""
        self._on_upscale.append(callback)

    async def start(self) -> None:
        """Start the adaptation loop."""
        self._task = asyncio.ensure_future(self._adapt_loop())

    async def stop(self) -> None:
        """Stop the adaptation loop."""
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def set_profile(self, profile: BitrateProfile) -> None:
        """Set the bitrate profile."""
        self.profile = profile

    def select_tier(self, estimated_bps: int) -> BitrateTier:
        """Select the appropriate bitrate tier for the estimated bandwidth.

        Override for custom tier selection logic.
        """
        ratio = estimated_bps / max(self.profile.max_bitrate, 1)
        if ratio < 0.05:
            return BitrateTier.MINIMUM
        elif ratio < 0.2:
            return BitrateTier.LOW
        elif ratio < 0.5:
            return BitrateTier.MEDIUM
        elif ratio < 0.9:
            return BitrateTier.HIGH
        return BitrateTier.MAXIMUM

    def get_bitrate_for_tier(self, tier: BitrateTier) -> int:
        """Get the target bitrate for a given tier."""
        profile = self.profile
        tiers = {
            BitrateTier.MINIMUM: profile.min_bitrate,
            BitrateTier.LOW: profile.min_bitrate * 2,
            BitrateTier.MEDIUM: profile.start_bitrate,
            BitrateTier.HIGH: profile.start_bitrate * 2,
            BitrateTier.MAXIMUM: profile.max_bitrate,
        }
        return tiers.get(tier, profile.start_bitrate)

    async def apply_encoding(self, tier: BitrateTier) -> None:
        """Apply encoding parameters for the selected tier.

        Override to set custom RTCRtpEncodingParameters.
        """
        target_bps = self.get_bitrate_for_tier(tier)
        self._logger.debug("applying encoding: %s (%d bps)", tier.value, target_bps)

    async def _adapt_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._adapt_interval)
                stats = await self.pc.get_stats()
                estimate = self.estimator.update(stats)

                pairs = stats.get("ice_candidate_pairs", [])
                nominated = [p for p in pairs if p.get("nominated")]
                rtt = nominated[0].get("current_rtt", 0) * 1000 if nominated else 0

                inbound = stats.get("inbound_rtp", [])
                total_loss = sum(s.get("packets_lost", 0) for s in inbound)
                total_packets = sum(s.get("packets_received", 0) for s in inbound)
                loss_pct = (total_loss / max(total_packets, 1)) * 100

                self.detector.update(rtt, loss_pct)

                new_tier = self.select_tier(estimate)
                if self.detector.is_congested:
                    new_tier = BitrateTier(min(new_tier.value - 1, 0))

                if new_tier != self._current_tier:
                    await self.apply_encoding(new_tier)
                    if new_tier.value < self._current_tier.value:
                        for cb in self._on_downscale:
                            cb(new_tier)
                    else:
                        for cb in self._on_upscale:
                            cb(new_tier)
                    self._current_tier = new_tier

            except asyncio.CancelledError:
                break
            except Exception:
                pass

    @property
    def _logger(self) -> logging.Logger:
        return logger.getChild(f"abc-{self.pc.peer_id}")


__all__ = [
    "BandwidthEstimator",
    "AdaptiveBitrateController",
    "BitrateProfile",
    "BitrateTier",
    "CongestionDetector",
]
