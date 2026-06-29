"""
Metrics and monitoring integration for WebRTC.

Provides Prometheus-compatible metrics for tracking peer connections,
data channel traffic, ICE connection states, and errors.

Uses the ``prometheus_client`` library: ``pip install prometheus-client``

Usage::

    from rivex_adapter.webrtc.metrics import WebRTCMetrics

    metrics = WebRTCMetrics(namespace="myapp")

    # Attach to a peer connection
    pc = WebRTCPeerConnection(peer_id="alice")
    metrics.monitor(pc)

    # Expose metrics endpoint (standard Prometheus)
    from prometheus_client import start_http_server
    start_http_server(8000)

If ``prometheus_client`` is not installed, all operations are no-ops.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger

try:
    from prometheus_client import Counter, Gauge, Histogram, Summary

    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False


class _NoOpMetric:
    """No-op metric when prometheus_client is not installed."""

    def labels(self, **kwargs: Any) -> _NoOpMetric:
        return self

    def inc(self, amount: float = 1.0) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass

    def set(self, value: float) -> None:
        pass

    def dec(self, amount: float = 1.0) -> None:
        pass


def _metric(cls: Any, name: str, documentation: str, **kwargs: Any) -> Any:
    """Create a real or no-op metric depending on prometheus availability."""
    if not _HAS_PROMETHEUS:
        return _NoOpMetric()
    return cls(name, documentation, **kwargs)


class WebRTCMetrics:
    """Prometheus metrics for WebRTC peer connections.

    Tracks:
    - ``{namespace}_webrtc_connections_total`` — total connections created
    - ``{namespace}_webrtc_connections_active`` — currently active connections
    - ``{namespace}_webrtc_connection_state`` — per-state connection count
    - ``{namespace}_webrtc_data_channel_messages_sent`` — messages sent
    - ``{namespace}_webrtc_data_channel_messages_received`` — messages received
    - ``{namespace}_webrtc_data_channel_bytes_sent`` — bytes sent
    - ``{namespace}_webrtc_data_channel_bytes_received`` — bytes received
    - ``{namespace}_webrtc_ice_restarts_total`` — ICE restarts
    - ``{namespace}_webrtc_errors_total`` — errors by type
    - ``{namespace}_webrtc_ice_rtt_seconds`` — RTT histogram

    All counters have a ``peer_id`` label.

    Usage::

        metrics = WebRTCMetrics(namespace="my_app")
        metrics.monitor(pc)

        # Manual reporting:
        metrics.connections_active.inc()
    """

    def __init__(self, namespace: str = "rivex"):
        self.namespace = namespace

        if not _HAS_PROMETHEUS:
            self._noop = _NoOpMetric()
            self.connections_total = self._noop
            self.connections_active = self._noop
            self.connection_state = self._noop
            self.messages_sent = self._noop
            self.messages_received = self._noop
            self.bytes_sent = self._noop
            self.bytes_received = self._noop
            self.ice_restarts_total = self._noop
            self.errors_total = self._noop
            self.ice_rtt_seconds = self._noop
            return

        self.connections_total = Counter(
            f"{namespace}_webrtc_connections_total",
            "Total WebRTC peer connections created",
            ["peer_id"],
        )
        self.connections_active = Gauge(
            f"{namespace}_webrtc_connections_active",
            "Currently active WebRTC peer connections",
            ["peer_id"],
        )
        self.connection_state = Gauge(
            f"{namespace}_webrtc_connection_state",
            "WebRTC connection state (1 = active)",
            ["peer_id", "state"],
        )
        self.messages_sent = Counter(
            f"{namespace}_webrtc_data_channel_messages_sent",
            "Data channel messages sent",
            ["peer_id", "channel"],
        )
        self.messages_received = Counter(
            f"{namespace}_webrtc_data_channel_messages_received",
            "Data channel messages received",
            ["peer_id", "channel"],
        )
        self.bytes_sent = Counter(
            f"{namespace}_webrtc_data_channel_bytes_sent",
            "Data channel bytes sent",
            ["peer_id", "channel"],
        )
        self.bytes_received = Counter(
            f"{namespace}_webrtc_data_channel_bytes_received",
            "Data channel bytes received",
            ["peer_id", "channel"],
        )
        self.ice_restarts_total = Counter(
            f"{namespace}_webrtc_ice_restarts_total",
            "Total ICE restarts performed",
            ["peer_id"],
        )
        self.errors_total = Counter(
            f"{namespace}_webrtc_errors_total",
            "WebRTC errors by type",
            ["peer_id", "error_type"],
        )
        self.ice_rtt_seconds = Histogram(
            f"{namespace}_webrtc_ice_rtt_seconds",
            "ICE round-trip time in seconds",
            ["peer_id"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )

    # ------------------------------------------------------------------
    # Monitor a peer connection
    # ------------------------------------------------------------------

    def monitor(self, pc: WebRTCPeerConnection) -> None:
        """Attach metrics tracking to a peer connection.

        Wires into the peer's connection state, message, and
        ICE candidate callbacks.
        """
        peer_id = pc.peer_id

        if _HAS_PROMETHEUS:
            self.connections_total.labels(peer_id=peer_id).inc()
            self.connections_active.labels(peer_id=peer_id).set(1)

        def _on_state(state: str) -> None:
            if _HAS_PROMETHEUS:
                self.connection_state.labels(peer_id=peer_id, state=state).set(
                    1 if state in ("connected", "completed") else 0
                )
            if state in ("closed", "failed"):
                if _HAS_PROMETHEUS:
                    self.connections_active.labels(peer_id=peer_id).set(0)

        pc.on_connection_state(_on_state)

        original_on_message = pc._on_message

        def _wrapped_on_message(label: str, data: str | bytes) -> None:
            if original_on_message:
                original_on_message(label, data)
            if _HAS_PROMETHEUS:
                self.messages_received.labels(
                    peer_id=peer_id, channel=label
                ).inc()
                size = len(data) if isinstance(data, bytes) else len(data.encode())
                self.bytes_received.labels(
                    peer_id=peer_id, channel=label
                ).inc(size)

        pc._on_message = _wrapped_on_message

        original_create_channel = pc.create_data_channel

        def _wrapped_create_channel(
            label: str,
            ordered: bool = True,
            max_retransmits: int | None = None,
        ) -> Any:
            channel = original_create_channel(label, ordered, max_retransmits)
            original_send = channel.send

            def _wrapped_send(data: str | bytes) -> None:
                original_send(data)
                if _HAS_PROMETHEUS:
                    self.messages_sent.labels(
                        peer_id=peer_id, channel=label
                    ).inc()
                    size = (
                        len(data) if isinstance(data, bytes)
                        else len(data.encode())
                    )
                    self.bytes_sent.labels(
                        peer_id=peer_id, channel=label
                    ).inc(size)

            channel.send = _wrapped_send
            return channel

        pc.create_data_channel = _wrapped_create_channel

        original_ice_restart = pc.ice_restart

        async def _wrapped_ice_restart() -> dict[str, Any]:
            result = await original_ice_restart()
            if _HAS_PROMETHEUS:
                self.ice_restarts_total.labels(peer_id=peer_id).inc()
            return result

        pc.ice_restart = _wrapped_ice_restart

    # ------------------------------------------------------------------
    # Manual error reporting
    # ------------------------------------------------------------------

    def record_error(
        self,
        peer_id: str,
        error_type: str = "unknown",
    ) -> None:
        """Record a WebRTC error.

        Args:
            peer_id: The peer that experienced the error.
            error_type: Error category (e.g. ``"ice_failure"``,
                ``"signaling_error"``, ``"data_channel_error"``).
        """
        if _HAS_PROMETHEUS:
            self.errors_total.labels(
                peer_id=peer_id, error_type=error_type
            ).inc()

    def record_rtt(self, peer_id: str, rtt_seconds: float) -> None:
        """Record an ICE round-trip time observation."""
        if _HAS_PROMETHEUS:
            self.ice_rtt_seconds.labels(peer_id=peer_id).observe(rtt_seconds)

    # ------------------------------------------------------------------
    # Unmonitor / cleanup
    # ------------------------------------------------------------------

    def unmonitor(self, pc: WebRTCPeerConnection) -> None:
        """Remove metrics tracking from a peer connection.

        Note: this does not undo the callback wiring. For proper
        cleanup, call before ``pc.close()``.
        """
        if _HAS_PROMETHEUS:
            self.connections_active.labels(peer_id=pc.peer_id).set(0)
            self.connection_state.labels(
                peer_id=pc.peer_id, state="closed"
            ).set(1)


__all__ = [
    "WebRTCMetrics",
]
