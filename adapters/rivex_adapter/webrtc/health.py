"""
Connection health monitoring, keep-alive, and reconnection for WebRTC.

Provides:
- ``ConnectionHealthMonitor`` — monitors connection health, triggers reconnection
- ``KeepAlive`` — periodic ping/pong over data channels
- ``ReconnectionPolicy`` — exponential backoff reconnection strategy
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, SignalingMessage, SignalingMessageType, logger


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DISCONNECTED = "disconnected"
    RECOVERING = "recovering"


@dataclass
class ReconnectionPolicy:
    """Exponential backoff reconnection policy.

    Override ``next_delay()`` to implement custom backoff logic.
    """

    max_retries: int = 5
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter_factor: float = 0.1

    def next_delay(self, attempt: int) -> float:
        """Compute delay in seconds before the *attempt*-th retry.

        Default: exponential backoff with jitter::

            delay = min(base * 2^attempt, max) * (1 + random(-jitter, jitter))
        """
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        jitter = delay * self.jitter_factor * random.uniform(-1.0, 1.0)
        return max(0.1, delay + jitter)


class KeepAlive:
    """Periodic keep-alive pings over a WebRTC data channel.

    Sends ``SignalingMessageType.PING`` messages and expects
    ``SignalingMessageType.PONG`` responses. Tracks round-trip time
    and missed pongs.

    Usage::

        ka = KeepAlive(pc, channel_label="health")
        ka.on_timeout(lambda rtt: print(f"RTT: {rtt:.0f}ms"))
        await ka.start()
        # ...
        await ka.stop()

    Extensibility:
        Override ``send_ping()`` or ``on_pong_timeout()`` to customize.
    """

    def __init__(
        self,
        pc: WebRTCPeerConnection,
        channel_label: str = "keepalive",
        interval: float = 5.0,
        timeout: float = 10.0,
    ):
        self.pc = pc
        self.channel_label = channel_label
        self.interval = interval
        self.timeout = timeout
        self._channel: Any = None
        self._task: asyncio.Task[None] | None = None
        self._pending_ping: float | None = None
        self._missed_pongs: int = 0
        self._rtt_callbacks: list[Callable[[float], None]] = []
        self._missed_callbacks: list[Callable[[int], None]] = []
        self._logger = logger.getChild(f"keepalive-{pc.peer_id}")

    def on_rtt(self, callback: Callable[[float], None]) -> None:
        """Called with round-trip time in seconds when a pong arrives."""
        self._rtt_callbacks.append(callback)

    def on_missed(self, callback: Callable[[int], None]) -> None:
        """Called with consecutive missed pong count."""
        self._missed_callbacks.append(callback)

    async def start(self) -> None:
        """Start sending periodic keep-alive pings."""
        if self.channel_label in self.pc._data_channels:
            self._channel = self.pc._data_channels[self.channel_label]
        else:
            self._channel = self.pc.create_data_channel(
                self.channel_label, ordered=True
            )

        self._wire_receiver()
        self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        """Stop the keep-alive loop."""
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.interval)
                self._pending_ping = time.time()
                await self.send_ping()
                await asyncio.sleep(self.timeout)

                if self._pending_ping is not None:
                    elapsed = time.time() - self._pending_ping
                    if elapsed >= self.timeout:
                        self._missed_pongs += 1
                        self._logger.warning(
                            "missed pong #%d (%.1fs)", self._missed_pongs, elapsed
                        )
                        for cb in self._missed_callbacks:
                            cb(self._missed_pongs)
            except asyncio.CancelledError:
                break
            except Exception:
                self._logger.exception("keepalive error")

    async def send_ping(self) -> None:
        """Send a ping message.

        Override to customise the ping format.
        """
        self._channel.send(str(time.time()))

    def _wire_receiver(self) -> None:
        original = self.pc._on_message
        def _on_message(label: str, data: str | bytes) -> None:
            if label == self.channel_label and self._pending_ping is not None:
                try:
                    sent_time = float(data) if isinstance(data, (str, bytes)) else 0.0
                    rtt = time.time() - sent_time
                    self._pending_ping = None
                    self._missed_pongs = 0
                    for cb in self._rtt_callbacks:
                        cb(rtt)
                except (ValueError, TypeError):
                    pass
            if original:
                original(label, data)
        self.pc._on_message = _on_message


class ConnectionHealthMonitor:
    """Monitor WebRTC connection health and trigger reconnection.

    Combines connection state tracking, keep-alive, and
    exponential-backoff reconnection into a single monitor.

    Usage::

        health = ConnectionHealthMonitor(pc)
        health.on_status_change(lambda s: print(f"Status: {s.value}"))
        await health.start()

        # If the connection drops, the monitor automatically
        # waits and calls the reconnect callback.
        health.on_reconnect(lambda: print("Reconnecting..."))

        await health.stop()

    Extensibility:
        Override ``on_reconnecting()``, ``perform_reconnect()``,
        or ``compute_health()`` to customize.
    """

    def __init__(
        self,
        pc: WebRTCPeerConnection,
        keepalive: KeepAlive | None = None,
        reconnection_policy: ReconnectionPolicy | None = None,
    ):
        self.pc = pc
        self.keepalive = keepalive or KeepAlive(pc)
        self.policy = reconnection_policy or ReconnectionPolicy()
        self._status: HealthStatus = HealthStatus.HEALTHY
        self._reconnect_attempt = 0
        self._status_callbacks: list[Callable[[HealthStatus], None]] = []
        self._reconnect_callbacks: list[Callable[[], None]] = []
        self._recovery_callbacks: list[Callable[[], None]] = []
        self._task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._stopped = False
        self._logger = logger.getChild(f"health-{pc.peer_id}")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_status_change(self, callback: Callable[[HealthStatus], None]) -> None:
        """Called when the overall health status changes."""
        self._status_callbacks.append(callback)

    def on_reconnect(self, callback: Callable[[], None]) -> None:
        """Called when a reconnection attempt is starting."""
        self._reconnect_callbacks.append(callback)

    def on_recovery(self, callback: Callable[[], None]) -> None:
        """Called when the connection recovers after a failure."""
        self._recovery_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start health monitoring."""
        self.pc.on_connection_state(self._on_state)
        self.keepalive.on_missed(self._on_missed)

        await self.keepalive.start()
        self._task = asyncio.ensure_future(self._monitor_loop())
        self._logger.info("health monitoring started")

    async def stop(self) -> None:
        """Stop health monitoring."""
        self._stopped = True
        await self.keepalive.stop()
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            self._reconnect_task = None

    @property
    def status(self) -> HealthStatus:
        """Current health status."""
        return self._status

    # ------------------------------------------------------------------
    # Extensibility hooks
    # ------------------------------------------------------------------

    def compute_health(self, state: str, missed_pongs: int) -> HealthStatus:
        """Determine the overall health status.

        Override for custom health scoring logic.
        """
        if state == "connected" and missed_pongs == 0:
            return HealthStatus.HEALTHY
        if state == "connected" and missed_pongs > 0:
            return HealthStatus.DEGRADED
        if state == "disconnected":
            return HealthStatus.DISCONNECTED
        if state == "failed":
            return HealthStatus.UNHEALTHY
        if self._reconnect_attempt > 0:
            return HealthStatus.RECOVERING
        return HealthStatus.DEGRADED

    async def on_reconnecting(self) -> None:
        """Called before reconnection starts.

        Override to add pre-reconnect logic (metrics, logging).
        """
        self._logger.info(
            "reconnecting (attempt %d/%d)",
            self._reconnect_attempt, self.policy.max_retries,
        )

    async def perform_reconnect(self) -> bool:
        """Execute the actual reconnection.

        Override to implement custom reconnection (e.g., new signaling).
        Default triggers an ICE restart.
        """
        try:
            await self.pc.ice_restart()
            return True
        except Exception as e:
            self._logger.error("reconnect failed: %s", e)
            return False

    async def on_recovered(self) -> None:
        """Called after successful reconnection."""
        self._reconnect_attempt = 0
        for cb in self._recovery_callbacks:
            cb()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_state(self, state: str) -> None:
        self._update_status()

    def _on_missed(self, count: int) -> None:
        if count >= 2:
            self._update_status()
            if self._status in (HealthStatus.UNHEALTHY, HealthStatus.DISCONNECTED):
                self._start_reconnect()

    def _update_status(self) -> None:
        state = self.pc.connection_state
        missed = self.keepalive._missed_pongs
        new_status = self.compute_health(state, missed)

        if new_status != self._status:
            old = self._status
            self._status = new_status
            self._logger.info("health: %s -> %s", old.value, new_status.value)
            for cb in self._status_callbacks:
                cb(new_status)

    def _start_reconnect(self) -> None:
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.ensure_future(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        while self._reconnect_attempt < self.policy.max_retries:
            await self.on_reconnecting()

            for cb in self._reconnect_callbacks:
                cb()

            success = await self.perform_reconnect()

            if success:
                await asyncio.sleep(1)
                if self.pc.connection_state == "connected":
                    await self.on_recovered()
                    self._update_status()
                    return

            self._reconnect_attempt += 1
            delay = self.policy.next_delay(self._reconnect_attempt)
            self._logger.warning(
                "reconnect attempt %d failed, retrying in %.1fs",
                self._reconnect_attempt, delay,
            )
            await asyncio.sleep(delay)

    async def _monitor_loop(self) -> None:
        while not self._stopped:
            try:
                await asyncio.sleep(1)
                self._update_status()
            except asyncio.CancelledError:
                break
            except Exception:
                pass


__all__ = [
    "ConnectionHealthMonitor",
    "KeepAlive",
    "ReconnectionPolicy",
    "HealthStatus",
]
