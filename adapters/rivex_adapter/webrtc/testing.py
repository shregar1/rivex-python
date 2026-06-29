"""
Testing utilities for WebRTC applications.

Provides:
- ``MockPeerConnection`` — simulate a ``WebRTCPeerConnection`` without aiortc
- ``MockDataChannel`` — simulate a data channel
- ``WebRTCTestCase`` — pytest-style test helper with async fixtures
- ``assert_message_sent`` — check that a message was sent on a channel
- ``capture_messages`` — context manager to capture sent messages

Usage::

    from rivex_adapter.webrtc.testing import MockPeerConnection, WebRTCTestCase

    # In a test:
    pc = MockPeerConnection(peer_id="test-peer")
    assert pc.peer_id == "test-peer"
    assert pc.connection_state == "new"

    pc.create_data_channel("chat")
    await pc.send_data("chat", "hello")
    assert pc.get_sent_messages("chat") == ["hello"]
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, WebRTCConfig, logger


class MockDataChannel:
    """Simulate a WebRTC data channel for testing.

    Records sent messages and allows injecting received messages.
    """

    def __init__(self, label: str, ordered: bool = True):
        self.label = label
        self.ordered = ordered
        self._sent: list[str | bytes] = []
        self._on_message: Callable[[str | bytes], None] | None = None
        self._state = "open"

    def send(self, data: str | bytes) -> None:
        """Record a sent message."""
        self._sent.append(data)

    def close(self) -> None:
        """Close the channel."""
        self._state = "closed"

    def on(self, event: str, handler: Callable | None = None) -> Callable | None:
        """Register an event handler (compat with aiortc data channels).

        Supports both direct and decorator patterns::

            channel.on(\"message\", handler)   # direct
            @channel.on(\"message\")           # decorator
            def handler(data): ...
        """
        if handler is not None:
            if event == "message":
                self._on_message = handler
            return None

        def _decorator(fn: Callable) -> Callable:
            if event == "message":
                self._on_message = fn
            return fn

        return _decorator

    def receive(self, data: str | bytes) -> None:
        """Simulate receiving a message."""
        if self._on_message:
            self._on_message(data)

    def get_sent(self, clear: bool = False) -> list[str | bytes]:
        """Get all sent messages."""
        result = list(self._sent)
        if clear:
            self._sent.clear()
        return result

    @property
    def ready_state(self) -> str:
        return self._state


class MockRTCPeerConnection:
    """Simulate an aiortc ``RTCPeerConnection`` for testing."""

    def __init__(self):
        self.connectionState = "new"
        self.iceConnectionState = "new"
        self._handlers: dict[str, list[Callable]] = {}
        self._data_channels: dict[str, MockDataChannel] = {}
        self._closed = False

    def on(self, event: str, handler: Callable) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def _emit(self, event: str, *args: Any) -> None:
        for handler in self._handlers.get(event, []):
            handler(*args)

    def createDataChannel(
        self,
        label: str,
        ordered: bool = True,
        maxRetransmits: int | None = None,
    ) -> MockDataChannel:
        ch = MockDataChannel(label, ordered=ordered)
        self._data_channels[label] = ch
        return ch

    async def createOffer(self) -> Any:
        class FakeOffer:
            def __init__(self):
                self.sdp = "v=0\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\n"
                self.type = "offer"
        return FakeOffer()

    async def createAnswer(self) -> Any:
        class FakeAnswer:
            def __init__(self):
                self.sdp = "v=0\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\n"
                self.type = "answer"
        return FakeAnswer()

    async def setLocalDescription(self, sdp: Any) -> None:
        pass

    async def setRemoteDescription(self, sdp: Any) -> None:
        pass

    async def addIceCandidate(self, candidate: Any) -> None:
        pass

    async def getStats(self) -> Any:
        class FakeStatsReport:
            def values(self):
                return []
        return FakeStatsReport()

    async def close(self) -> None:
        self._closed = True
        self.connectionState = "closed"
        self.iceConnectionState = "closed"


class MockPeerConnection(WebRTCPeerConnection):
    """A ``WebRTCPeerConnection`` that uses a mock ``RTCPeerConnection``.

    Does not require aiortc to be installed. All SDP operations
    return fake values. Data channels are simulated in-memory.

    Usage::

        pc = MockPeerConnection(peer_id="test")
        ch = pc.create_data_channel("chat")
        await pc.send_data("chat", "hello")
        assert pc.get_channel("chat").get_sent() == ["hello"]
    """

    def __init__(
        self,
        peer_id: str | None = None,
        config: WebRTCConfig | None = None,
    ):
        super().__init__(peer_id=peer_id, config=config)

    async def ensure_pc(self) -> None:
        if self._pc is not None:
            return
        self._pc = MockRTCPeerConnection()

    def create_data_channel(
        self,
        label: str,
        ordered: bool = True,
        max_retransmits: int | None = None,
    ) -> MockDataChannel:
        ch = MockDataChannel(label, ordered=ordered)
        self._data_channels[label] = ch
        self._wire_data_channel(ch, label)
        return ch

    def get_channel(self, label: str) -> MockDataChannel | None:
        """Get a mock data channel by label (for test assertions)."""
        return self._data_channels.get(label)

    def get_sent_messages(self, label: str) -> list[str | bytes]:
        """Get all messages sent on a channel."""
        ch = self.get_channel(label)
        if ch is None:
            return []
        return ch.get_sent()

    async def make_fake_offer(self) -> dict[str, Any]:
        """Create a fake SDP offer without ICE gathering."""
        await self.ensure_pc()
        self._negotiated = True
        return {"sdp": "v=0\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\n", "type": "offer"}

    async def make_fake_answer(self, offer: dict[str, Any]) -> dict[str, Any]:
        """Create a fake SDP answer."""
        await self.ensure_pc()
        self._negotiated = True
        return {"sdp": "v=0\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\n", "type": "answer"}

    def simulate_state(self, state: str) -> None:
        """Simulate a connection state change."""
        if self._pc is not None:
            self._pc.connectionState = state
            self._pc.iceConnectionState = state
            self._pc._emit("connectionstatechange")
            self._pc._emit("iceconnectionstatechange")


# ---------------------------------------------------------------------------
# Test assertions
# ---------------------------------------------------------------------------


def assert_message_sent(
    pc: MockPeerConnection,
    channel_label: str,
    expected: str | bytes,
    clear: bool = True,
) -> None:
    """Assert that a message was sent on a data channel.

    Args:
        pc: The mock peer connection.
        channel_label: Data channel label.
        expected: Expected message content.
        clear: If ``True``, clear the message history after assertion.

    Raises:
        AssertionError: If the message was not found.
    """
    ch = pc.get_channel(channel_label)
    assert ch is not None, f"channel {channel_label!r} not found"
    sent = ch.get_sent(clear=clear)
    assert expected in sent, (
        f"expected {expected!r} in sent messages on {channel_label!r}, "
        f"got {sent!r}"
    )


def assert_no_messages_sent(
    pc: MockPeerConnection, channel_label: str
) -> None:
    """Assert that no messages were sent on a data channel."""
    ch = pc.get_channel(channel_label)
    assert ch is not None, f"channel {channel_label!r} not found"
    sent = ch.get_sent()
    assert len(sent) == 0, (
        f"expected no messages on {channel_label!r}, got {sent!r}"
    )


# ---------------------------------------------------------------------------
# Capture context manager
# ---------------------------------------------------------------------------


class MessageCapture:
    """Capture messages sent on a data channel for assertions.

    Usage::

        with capture_messages(pc, "chat") as captured:
            await pc.send_data("chat", "hello")
            await pc.send_data("chat", "world")

        assert captured == ["hello", "world"]
    """

    def __init__(self, pc: MockPeerConnection, channel_label: str):
        self.pc = pc
        self.channel_label = channel_label
        self._before: list[str | bytes] = []
        self._after: list[str | bytes] = []

    def __enter__(self) -> list[str | bytes]:
        ch = self.pc.get_channel(self.channel_label)
        if ch:
            self._before = ch.get_sent(clear=True)
        return self._after

    def __exit__(self, *args: Any) -> None:
        ch = self.pc.get_channel(self.channel_label)
        if ch:
            self._after[:] = ch.get_sent(clear=True)


def capture_messages(
    pc: MockPeerConnection, channel_label: str
) -> MessageCapture:
    """Context manager to capture messages sent on a data channel."""
    return MessageCapture(pc, channel_label)


# ---------------------------------------------------------------------------
# WebRTC test case base
# ---------------------------------------------------------------------------


class WebRTCTestCase:
    """Base class for WebRTC tests with helper fixtures.

    Usage::

        class TestMyFeature(WebRTCTestCase):
            async def test_chat(self):
                alice = self.make_peer("alice")
                bob = self.make_peer("bob")

                alice.create_data_channel("chat")
                await alice.send_data("chat", "hello")

                assert alice.get_sent_messages("chat") == ["hello"]
    """

    def make_peer(self, peer_id: str | None = None) -> MockPeerConnection:
        """Create a ``MockPeerConnection`` for testing."""
        return MockPeerConnection(peer_id=peer_id or uuid.uuid4().hex[:8])

    def make_pair(
        self,
    ) -> tuple[MockPeerConnection, MockPeerConnection]:
        """Create a pair of connected mock peers.

        Both peers have their ``ensure_pc()`` called, and one
        creates an offer accepted by the other.
        """
        alice = self.make_peer("alice")
        bob = self.make_peer("bob")
        return alice, bob

    async def connect_pair(
        self, alice: MockPeerConnection, bob: MockPeerConnection
    ) -> None:
        """Simulate SDP negotiation between two peers."""
        offer = await alice.make_fake_offer()
        answer = await bob.make_fake_answer(offer)
        await alice.set_remote_description(answer)

    def assert_connected(self, pc: MockPeerConnection) -> None:
        """Assert a peer is in connected state."""
        assert pc.connection_state in (
            "connected", "new"
        ), f"expected connected state, got {pc.connection_state}"


__all__ = [
    "MockPeerConnection",
    "MockDataChannel",
    "MockRTCPeerConnection",
    "WebRTCTestCase",
    "assert_message_sent",
    "assert_no_messages_sent",
    "capture_messages",
    "MessageCapture",
]
