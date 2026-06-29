"""
Network condition simulator for WebRTC testing.

Simulates real-world network conditions: latency, jitter, packet loss,
and bandwidth constraints on data channels and media tracks.

Provides:
- ``NetworkSimulator`` — apply network conditions to a peer connection
- ``LatencySimulator`` — add latency and jitter
- ``PacketLossSimulator`` — drop packets with configurable probability
- ``BandwidthLimiter`` — throttle bandwidth with token bucket
- ``NetworkProfile`` — named presets (3G, 4G, WiFi, etc.)

Usage::

    from rivex_adapter.webrtc import NetworkSimulator, NetworkProfile

    sim = NetworkSimulator()

    # Apply a 3G profile to a peer connection
    sim.apply(pc, NetworkProfile.THREE_G)

    # Or custom conditions
    sim.apply(pc, NetworkProfile(
        latency_ms=100,
        jitter_ms=20,
        packet_loss=0.05,
        bandwidth_kbps=500,
    ))

    # Remove simulation
    sim.remove(pc)

Extensibility:
    Subclass and override ``should_drop()``, ``apply_latency()``,
    or ``throttle()`` for custom simulation logic.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger


@dataclass
class NetworkProfile:
    """A named network condition profile.

    Presets::

        NetworkProfile.THREE_G    — 100ms latency, 10% loss, 1.6 Mbps
        NetworkProfile.FOUR_G     — 50ms latency, 2% loss, 10 Mbps
        NetworkProfile.WIFI       — 20ms latency, 1% loss, 50 Mbps
        NetworkProfile.ETHERNET   — 5ms latency, 0.1% loss, 1 Gbps
        NetworkProfile.SATELLITE  — 600ms latency, 5% loss, 20 Mbps
        NetworkProfile.PERFECT    — no impairments
    """

    name: str = "custom"
    latency_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss: float = 0.0
    bandwidth_kbps: float = 0.0

    THREE_G: "NetworkProfile" = None
    FOUR_G: "NetworkProfile" = None
    WIFI: "NetworkProfile" = None
    ETHERNET: "NetworkProfile" = None
    SATELLITE: "NetworkProfile" = None
    PERFECT: "NetworkProfile" = None


NetworkProfile.THREE_G = NetworkProfile(
    name="3G", latency_ms=100, jitter_ms=30, packet_loss=0.10, bandwidth_kbps=1600
)
NetworkProfile.FOUR_G = NetworkProfile(
    name="4G", latency_ms=50, jitter_ms=10, packet_loss=0.02, bandwidth_kbps=10000
)
NetworkProfile.WIFI = NetworkProfile(
    name="WiFi", latency_ms=20, jitter_ms=5, packet_loss=0.01, bandwidth_kbps=50000
)
NetworkProfile.ETHERNET = NetworkProfile(
    name="Ethernet", latency_ms=5, jitter_ms=1, packet_loss=0.001, bandwidth_kbps=1_000_000
)
NetworkProfile.SATELLITE = NetworkProfile(
    name="Satellite", latency_ms=600, jitter_ms=50, packet_loss=0.05, bandwidth_kbps=20000
)
NetworkProfile.PERFECT = NetworkProfile(
    name="Perfect", latency_ms=0, jitter_ms=0, packet_loss=0.0, bandwidth_kbps=0
)


class LatencySimulator:
    """Add configurable latency and jitter to data channels.

    Intercepts data channel sends and adds artificial delay.
    """

    def __init__(self, latency_ms: float = 0.0, jitter_ms: float = 0.0):
        self.latency_ms = latency_ms
        self.jitter_ms = jitter_ms

    def apply_latency(self, size: int = 0) -> float:
        """Compute the delay in seconds for a message of *size* bytes.

        Override for custom latency modeling.
        """
        delay = self.latency_ms
        if self.jitter_ms > 0:
            delay += random.uniform(-self.jitter_ms, self.jitter_ms)
        return max(0, delay / 1000.0)


class PacketLossSimulator:
    """Drop packets with a configurable probability."""

    def __init__(self, loss_probability: float = 0.0):
        self.loss_probability = loss_probability

    def should_drop(self, size: int = 0) -> bool:
        """Return ``True`` if this packet should be dropped.

        Override for custom drop patterns (burst loss, etc.).
        """
        return random.random() < self.loss_probability


class BandwidthLimiter:
    """Throttle bandwidth using a token bucket algorithm."""

    def __init__(self, kbps: float = 0.0):
        self.kbps = kbps
        self._tokens = 0.0
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def is_limited(self) -> bool:
        return self.kbps > 0

    async def throttle(self, size_bytes: int) -> None:
        """Wait until enough tokens are available to send *size_bytes*."""
        if not self.is_limited:
            return

        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens += elapsed * self.kbps * 128  # bytes
            self._tokens = min(self._tokens, self.kbps * 128 * 5)
            self._last_refill = now

            needed = size_bytes
            if self._tokens < needed:
                wait = (needed - self._tokens) / (self.kbps * 128)
                self._tokens = 0
                await asyncio.sleep(wait)
            else:
                self._tokens -= needed


class NetworkSimulator:
    """Apply realistic network conditions to a peer connection.

    Simulates latency, jitter, packet loss, and bandwidth constraints
    on data channel sends.

    Usage::

        sim = NetworkSimulator()

        # Apply 4G conditions
        sim.apply(pc, NetworkProfile.FOUR_G)

        # Or use shorthand
        sim.apply_3g(pc)

        # Remove simulation
        sim.remove(pc)

    Extensibility:
        Override ``wrap_data_channel()`` or ``wrap_track()`` to
        customise how messages/frames are intercepted.
    """

    def __init__(self):
        self._profiles: dict[str, NetworkProfile] = {}
        self._latency: dict[str, LatencySimulator] = {}
        self._loss: dict[str, PacketLossSimulator] = {}
        self._bandwidth: dict[str, BandwidthLimiter] = {}
        self._originals: dict[str, dict[str, Any]] = {}
        self._logger = logger.getChild("network-sim")

    def apply(self, pc: WebRTCPeerConnection, profile: NetworkProfile) -> None:
        """Apply a network profile to a peer connection.

        Intercepts data channel sends to add simulated conditions.
        """
        pid = pc.peer_id
        self._profiles[pid] = profile
        self._latency[pid] = LatencySimulator(profile.latency_ms, profile.jitter_ms)
        self._loss[pid] = PacketLossSimulator(profile.packet_loss)
        self._bandwidth[pid] = BandwidthLimiter(profile.bandwidth_kbps)

        self._wrap_data_channels(pc)
        self._logger.info(
            "applied %s to %s (lat=%dms, loss=%.1f%%, bw=%dkbps)",
            profile.name, pid, profile.latency_ms,
            profile.packet_loss * 100, profile.bandwidth_kbps,
        )

    def remove(self, pc: WebRTCPeerConnection) -> None:
        """Remove network simulation from a peer connection."""
        pid = pc.peer_id
        self._profiles.pop(pid, None)
        self._latency.pop(pid, None)
        self._loss.pop(pid, None)
        self._bandwidth.pop(pid, None)

        originals = self._originals.pop(pid, None)
        if originals is not None:
            for label, original_send in originals.items():
                ch = pc._data_channels.get(label)
                if ch is not None and hasattr(ch, "send"):
                    ch.send = original_send

        self._logger.info("removed simulation from %s", pid)

    def apply_3g(self, pc: WebRTCPeerConnection) -> None:
        """Apply 3G network profile."""
        self.apply(pc, NetworkProfile.THREE_G)

    def apply_4g(self, pc: WebRTCPeerConnection) -> None:
        """Apply 4G network profile."""
        self.apply(pc, NetworkProfile.FOUR_G)

    def apply_wifi(self, pc: WebRTCPeerConnection) -> None:
        """Apply WiFi network profile."""
        self.apply(pc, NetworkProfile.WIFI)

    def apply_satellite(self, pc: WebRTCPeerConnection) -> None:
        """Apply satellite network profile."""
        self.apply(pc, NetworkProfile.SATELLITE)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _wrap_data_channels(self, pc: WebRTCPeerConnection) -> None:
        pid = pc.peer_id
        originals = self._originals.setdefault(pid, {})

        for label, ch in list(pc._data_channels.items()):
            if hasattr(ch, "send"):
                original_send = ch.send
                originals[label] = original_send

                lat = self._latency[pid]
                loss = self._loss[pid]
                bw = self._bandwidth[pid]

                async def _wrapped_send(
                    data: str | bytes,
                    _original=original_send,
                    _lat=lat, _loss=loss, _bw=bw,
                ) -> None:
                    size = len(data) if isinstance(data, bytes) else len(data.encode())

                    if _loss.should_drop(size):
                        return

                    if _bw.is_limited:
                        await _bw.throttle(size)

                    delay = _lat.apply_latency(size)
                    if delay > 0:
                        await asyncio.sleep(delay)

                    _original(data)

                ch.send = _wrapped_send

    def wrap_track(self, track: Any, profile: NetworkProfile | None = None) -> Any:
        """Wrap a media track with network simulation.

        Media frames get latency/jitter/loss applied.
        Requires opencv-python or equivalent.
        """
        if profile is None:
            return track

        lat = LatencySimulator(profile.latency_ms, profile.jitter_ms)
        loss = PacketLossSimulator(profile.packet_loss)

        async def _recv() -> Any:
            if loss.should_drop():
                return await track.recv()

            delay = lat.apply_latency()
            if delay > 0:
                await asyncio.sleep(delay)

            return await track.recv()

        track.recv = _recv
        return track

    def get_profile(self, pc: WebRTCPeerConnection) -> NetworkProfile | None:
        """Get the currently applied network profile."""
        return self._profiles.get(pc.peer_id)

    def list_profiles(self) -> list[str]:
        """List names of all predefined profiles."""
        return ["3G", "4G", "WiFi", "Ethernet", "Satellite", "Perfect"]


__all__ = [
    "NetworkSimulator",
    "NetworkProfile",
    "LatencySimulator",
    "PacketLossSimulator",
    "BandwidthLimiter",
]
