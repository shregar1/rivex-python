"""
WHIP/WHEP protocol support — WebRTC Ingest Protocol (WHIP, RFC) and
WebRTC HTML Egress Protocol (WHEP).

``WHIPEndpoint`` — ingest endpoint that receives a WebRTC stream from
a browser/broadcaster via HTTP POST + SDP.

``WHEPEndpoint`` — egress endpoint that serves a WebRTC stream to a
player via HTTP GET + SDP.

Usage::

    from rivex import Rivex

    app = Rivex()

    # WHIP — broadcaster pushes a stream
    @app.post("/whip/{stream_id}")
    async def whip_ingest(stream_id: str, request: Request):
        sdp = await request.body()
        answer = await whip_endpoint.ingest(stream_id, sdp.decode())
        return Response(content=answer, media_type="application/sdp")

    # WHEP — viewer pulls a stream
    @app.get("/whep/{stream_id}")
    async def whep_egress(stream_id: str):
        sdp = await whep_endpoint.egress(stream_id)
        return Response(content=sdp, media_type="application/sdp")
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from rivex_adapter.webrtc.core import (
    WebRTCPeerConnection,
    WebRTCConfig,
    IceServer,
    SignalingMessage,
    logger,
)


@dataclass
class WHIPStream:
    """A WHIP ingest stream."""

    stream_id: str
    pc: WebRTCPeerConnection
    peer_id: str = ""
    sdp: str = ""
    ice_ufrag: str = ""
    ice_pwd: str = ""
    created_at: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class WHEPStream:
    """A WHEP egress stream."""

    stream_id: str
    pc: WebRTCPeerConnection
    sdp: str = ""
    created_at: float = 0.0
    viewers: int = 0


class WHIPEndpoint:
    """WHIP (WebRTC Ingest Protocol) endpoint.

    Receives SDP offers from broadcasters and returns SDP answers,
    establishing a WebRTC connection for media ingest.

    Usage::

        whip = WHIPEndpoint()
        answer_sdp = await whip.ingest("stream-1", offer_sdp)
    """

    def __init__(
        self,
        config: WebRTCConfig | None = None,
        ice_servers: list[IceServer] | None = None,
    ):
        self._config = config or WebRTCConfig()
        if ice_servers:
            self._config.ice_servers = ice_servers
        self._streams: dict[str, WHIPStream] = {}
        self._on_ingest: list[callable] = []
        self._on_stop: list[callable] = []
        self._logger = logger.getChild("whip")

    def on_ingest(self, callback: callable) -> None:
        self._on_ingest.append(callback)

    def on_stop(self, callback: callable) -> None:
        self._on_stop.append(callback)

    async def ingest(
        self,
        stream_id: str,
        offer_sdp: str,
        peer_id: str = "",
        metadata: dict | None = None,
    ) -> str:
        """Process a WHIP ingest request.

        Args:
            stream_id: Unique stream identifier.
            offer_sdp: SDP offer from broadcaster.
            peer_id: Optional peer identifier.
            metadata: Optional stream metadata.

        Returns:
            SDP answer for the broadcaster.
        """
        pc = WebRTCPeerConnection(config=self._config)
        ice_ufrag, ice_pwd = self._extract_ice_credentials(offer_sdp)

        stream = WHIPStream(
            stream_id=stream_id,
            pc=pc,
            peer_id=peer_id,
            sdp=offer_sdp,
            ice_ufrag=ice_ufrag,
            ice_pwd=ice_pwd,
            metadata=metadata or {},
        )
        self._streams[stream_id] = stream

        # Set remote description from offer
        offer = SignalingMessage(type="offer", sdp=offer_sdp)
        await pc.set_remote_description(offer)

        # Create and set local description (answer)
        answer = await pc.create_answer()
        await pc.set_local_description(answer)

        for cb in self._on_ingest:
            try:
                cb(stream)
            except Exception:
                self._logger.exception("on_ingest handler error")

        self._logger.info("WHIP ingest: %s", stream_id)
        return answer.sdp

    async def stop_ingest(self, stream_id: str) -> None:
        stream = self._streams.pop(stream_id, None)
        if stream is None:
            return
        await stream.pc.close()
        for cb in self._on_stop:
            try:
                cb(stream)
            except Exception:
                self._logger.exception("on_stop handler error")
        self._logger.info("WHIP ingest stopped: %s", stream_id)

    def get_stream(self, stream_id: str) -> WHIPStream | None:
        return self._streams.get(stream_id)

    def list_streams(self) -> list[WHIPStream]:
        return list(self._streams.values())

    @staticmethod
    def _extract_ice_credentials(sdp: str) -> tuple[str, str]:
        ufrag = ""
        pwd = ""
        for line in sdp.split("\n"):
            if line.startswith("a=ice-ufrag:"):
                ufrag = line.split(":", 1)[1].strip()
            if line.startswith("a=ice-pwd:"):
                pwd = line.split(":", 1)[1].strip()
        return ufrag, pwd


class WHEPEndpoint:
    """WHEP (WebRTC HTML Egress Protocol) endpoint.

    Returns SDP offers for viewers to consume a stream.

    Usage::

        whep = WHEPEndpoint()
        offer_sdp = await whep.egress("stream-1", viewer_sdp=None)
    """

    def __init__(
        self,
        config: WebRTCConfig | None = None,
        ice_servers: list[IceServer] | None = None,
    ):
        self._config = config or WebRTCConfig()
        if ice_servers:
            self._config.ice_servers = ice_servers
        self._streams: dict[str, WHEPStream] = {}
        self._on_viewer_join: list[callable] = []
        self._on_viewer_leave: list[callable] = []
        self._logger = logger.getChild("whep")

    def on_viewer_join(self, callback: callable) -> None:
        self._on_viewer_join.append(callback)

    def on_viewer_leave(self, callback: callable) -> None:
        self._on_viewer_leave.append(callback)

    async def egress(
        self,
        stream_id: str,
        viewer_sdp: str | None = None,
    ) -> str:
        """Handle a WHEP egress request.

        Args:
            stream_id: The stream to consume.
            viewer_sdp: Optional SDP from viewer (for renegotiation).

        Returns:
            SDP offer or answer for the viewer.
        """
        if stream_id not in self._streams:
            pc = WebRTCPeerConnection(config=self._config)
            stream = WHEPStream(stream_id=stream_id, pc=pc)
            self._streams[stream_id] = stream

            offer = await pc.create_offer()
            await pc.set_local_description(offer)
            stream.sdp = offer.sdp
            stream.viewers += 1

            for cb in self._on_viewer_join:
                try:
                    cb(stream)
                except Exception:
                    self._logger.exception("on_viewer_join error")
        else:
            self._streams[stream_id].viewers += 1

        self._logger.info("WHEP egress: %s (viewers: %d)", stream_id, self._streams[stream_id].viewers)
        return self._streams[stream_id].sdp

    async def stop_egress(self, stream_id: str) -> None:
        stream = self._streams.pop(stream_id, None)
        if stream is None:
            return
        await stream.pc.close()
        for cb in self._on_viewer_leave:
            try:
                cb(stream)
            except Exception:
                self._logger.exception("on_viewer_leave error")
        self._logger.info("WHEP egress stopped: %s", stream_id)

    def get_stream(self, stream_id: str) -> WHEPStream | None:
        return self._streams.get(stream_id)

    def list_streams(self) -> list[WHEPStream]:
        return list(self._streams.values())


__all__ = [
    "WHIPEndpoint",
    "WHEPEndpoint",
    "WHIPStream",
    "WHEPStream",
]
