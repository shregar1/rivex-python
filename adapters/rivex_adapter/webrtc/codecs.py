"""
Codec negotiation, SDP manipulation, and simulcast support for WebRTC.

Provides:
- ``SimulcastConfig`` — simulcast encoding configuration
- ``SimulcastManager`` — enable/disable simulcast via SDP munging
- ``CodecNegotiator`` — specify preferred codec order
- ``SDPFilter`` — add/remove codecs from SDP
- ``sdp_add_simulcast()`` — add simulcast to an SDP offer
- ``sdp_remove_codec()`` — remove a codec from SDP
- ``sdp_set_bitrate()`` — set max bitrate in SDP
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger


class SimulcastRid(Enum):
    """Simulcast RID (Restriction Identifier) values."""

    LOW = "l"
    MEDIUM = "m"
    HIGH = "h"


@dataclass
class SimulcastEncoding:
    """Encoding configuration for a simulcast layer."""

    rid: str
    max_bitrate: int
    max_framerate: float = 30.0
    scale_resolution_down_by: float = 1.0
    active: bool = True


@dataclass
class SimulcastConfig:
    """Simulcast configuration for a video track.

    Usage::

        config = SimulcastConfig(
            encodings=[
                SimulcastEncoding(rid="l", max_bitrate=150_000, scale_resolution_down_by=4.0),
                SimulcastEncoding(rid="m", max_bitrate=500_000, scale_resolution_down_by=2.0),
                SimulcastEncoding(rid="h", max_bitrate=1_500_000, scale_resolution_down_by=1.0),
            ],
        )
    """

    encodings: list[SimulcastEncoding] = field(default_factory=lambda: [
        SimulcastEncoding(rid="l", max_bitrate=150_000, scale_resolution_down_by=4.0),
        SimulcastEncoding(rid="m", max_bitrate=500_000, scale_resolution_down_by=2.0),
        SimulcastEncoding(rid="h", max_bitrate=1_500_000, scale_resolution_down_by=1.0),
    ])


class SimulcastManager:
    """Manage simulcast/SVC configuration for a peer connection.

    Wraps SDP munging helpers to enable simulcast on outgoing
    video tracks.

    Usage::

        manager = SimulcastManager()

        # Before creating offer:
        offer = await manager.create_simulcast_offer(pc)

        # Or modify an existing offer SDP:
        modified_sdp = manager.add_simulcast_to_sdp(offer_sdp)
    """

    def __init__(self, config: SimulcastConfig | None = None):
        self.config = config or SimulcastConfig()

    def add_simulcast_to_sdp(self, sdp: str) -> str:
        """Add simulcast attributes to a video SDP.

        Modifies the SDP to include ``a=simulcast:send`` and
        ``a=rid:...`` attributes for each encoding layer.
        """
        lines = sdp.split("\r\n")
        result: list[str] = []
        in_video_section = False
        has_rid = False

        for line in lines:
            if line.startswith("m=video"):
                in_video_section = True
                has_rid = False
            elif line.startswith("m=") and not line.startswith("m=video"):
                if in_video_section and not has_rid:
                    rids = [e.rid for e in self.config.encodings]
                    result.append(f"a=rid:{rids[0]} send")
                    result.append(f"a=rid:{rids[1]} send")
                    result.append(f"a=rid:{rids[2]} send")
                    result.append(f"a=simulcast:send {';'.join(rids)}")
                in_video_section = False

            if in_video_section and "a=rid:" in line:
                has_rid = True

            result.append(line)

        if in_video_section and not has_rid:
            rids = [e.rid for e in self.config.encodings]
            result.append(f"a=rid:{rids[0]} send")
            result.append(f"a=rid:{rids[1]} send")
            result.append(f"a=rid:{rids[2]} send")
            result.append(f"a=simulcast:send {';'.join(rids)}")

        return "\r\n".join(result)

    async def create_simulcast_offer(
        self, pc: WebRTCPeerConnection
    ) -> dict[str, Any]:
        """Create an SDP offer with simulcast attributes.

        Returns the modified SDP offer dict.
        """
        offer = await pc.create_offer()
        offer["sdp"] = self.add_simulcast_to_sdp(offer["sdp"])
        return offer

    def get_rtp_encodings(self) -> list[dict[str, Any]]:
        """Get ``RTCRtpEncodingParameters`` for use with ``addTrack()``.

        These encodings should be passed when adding a track to
        enable simulcast::

            sender = pc.addTrack(track, encodings=manager.get_rtp_encodings())
        """
        return [
            {
                "rid": e.rid,
                "maxBitrate": e.max_bitrate,
                "maxFramerate": e.max_framerate,
                "scaleResolutionDownBy": e.scale_resolution_down_by,
                "active": e.active,
            }
            for e in self.config.encodings
        ]


class CodecNegotiator:
    """Negotiate preferred codec order.

    Allows specifying which codecs to prefer and which to exclude
    from the SDP.

    Usage::

        negotiator = CodecNegotiator(
            prefer_video=["VP9", "H264"],
            prefer_audio=["opus"],
            exclude=["H265", "ulpfec"],
        )
        modified_sdp = negotiator.apply(sdp)
    """

    def __init__(
        self,
        prefer_video: list[str] | None = None,
        prefer_audio: list[str] | None = None,
        exclude: list[str] | None = None,
    ):
        self.prefer_video = prefer_video or []
        self.prefer_audio = prefer_audio or []
        self.exclude = exclude or []

    def apply(self, sdp: str) -> str:
        """Reorder and filter codecs in the SDP."""
        sdp = self._remove_codecs(sdp)
        sdp = self._reorder_codecs(sdp)
        return sdp

    def _remove_codecs(self, sdp: str) -> str:
        if not self.exclude:
            return sdp

        lines = sdp.split("\r\n")
        result: list[str] = []
        in_media = False
        payloads_to_remove: set[str] = set()

        for line in lines:
            if line.startswith("m=video") or line.startswith("m=audio"):
                in_media = True
                parts = line.split(" ")
                pt_start = 3
                remaining: list[str] = []
                for pt in parts[pt_start:]:
                    if pt not in payloads_to_remove:
                        remaining.append(pt)
                line = " ".join(parts[:pt_start] + remaining)
                result.append(line)
            elif in_media and line.startswith("a=rtpmap:"):
                codec_name = line.split(" ", 1)[1] if " " in line else ""
                for exclude_name in self.exclude:
                    if exclude_name.lower() in codec_name.lower():
                        pt = line.split(":")[1].split(" ")[0]
                        payloads_to_remove.add(pt)
                        break
                result.append(line)
            elif in_media and line.startswith("m="):
                in_media = False
                result.append(line)
            else:
                result.append(line)

        result2: list[str] = []
        for line in result:
            if line.startswith("m=video") or line.startswith("m=audio"):
                parts = line.split(" ")
                pt_start = 3
                remaining = [pt for pt in parts[pt_start:] if pt not in payloads_to_remove]
                line = " ".join(parts[:pt_start] + remaining)
                result2.append(line)
            elif any(f":{pt} " in line for pt in payloads_to_remove):
                continue
            elif any(f"={pt}" in line for pt in payloads_to_remove):
                continue
            else:
                result2.append(line)

        return "\r\n".join(result2)

    def _reorder_codecs(self, sdp: str) -> str:
        prefers = {
            "video": self.prefer_video,
            "audio": self.prefer_audio,
        }

        lines = sdp.split("\r\n")
        result: list[str] = []
        i = 0

        while i < len(lines):
            line = lines[i]
            result.append(line)

            if line.startswith("m=video"):
                kind = "video"
                payload_start = i + 1
                payload_end = payload_start
                while payload_end < len(lines):
                    if lines[payload_end].startswith("m=") and not lines[payload_end].startswith("m=video"):
                        break
                    payload_end += 1

                rtpmap_lines = []
                for j in range(payload_start, payload_end):
                    if lines[j].startswith("a=rtpmap:"):
                        rtpmap_lines.append(lines[j])

                payload_order = []
                for pref_codec in prefers.get(kind, []):
                    for rline in rtpmap_lines:
                        codec_name = rline.split(" ", 1)[1] if " " in rline else ""
                        if pref_codec.lower() in codec_name.lower():
                            pt = rline.split(":")[1].split(" ")[0]
                            if pt not in payload_order:
                                payload_order.append(pt)

                if payload_order:
                    parts = line.split(" ")
                    codec_pts = [pt for pt in parts[3:] if pt in payload_order]
                    remaining = [pt for pt in parts[3:] if pt not in payload_order]
                    parts[3:] = codec_pts + remaining
                    result[-1] = " ".join(parts)

                i = payload_end - 1

            i += 1

        return "\r\n".join(result)

    def apply_to_pc(self, pc: WebRTCPeerConnection, sdp: str) -> str:
        """Apply codec negotiation to an SDP from a peer connection.

        Override for custom logic. Default delegates to ``apply()``.
        """
        return self.apply(sdp)


class SDPFilter:
    """Filter and manipulate SDP content.

    Provides both class methods for standalone SDP manipulation
    and instance methods for chaining operations.
    """

    @staticmethod
    def remove_codec(sdp: str, codec: str) -> str:
        """Remove a codec (by name or payload type) from SDP."""
        negotiator = CodecNegotiator(exclude=[codec])
        return negotiator.apply(sdp)

    @staticmethod
    def add_simulcast(sdp: str, rids: list[str] | None = None) -> str:
        """Add simulcast attributes to SDP."""
        rids = rids or ["l", "m", "h"]
        config = SimulcastConfig(encodings=[
            SimulcastEncoding(rid=rids[0], max_bitrate=150_000, scale_resolution_down_by=4.0),
            SimulcastEncoding(rid=rids[1], max_bitrate=500_000, scale_resolution_down_by=2.0),
            SimulcastEncoding(rid=rids[2], max_bitrate=1_500_000, scale_resolution_down_by=1.0),
        ])
        return SimulcastManager(config).add_simulcast_to_sdp(sdp)

    @staticmethod
    def set_bitrate(sdp: str, max_bitrate: int) -> str:
        """Set max bitrate (b=AS) in video sections of SDP."""
        return re.sub(
            r"(m=video.*\r?\n)(.*?)(?=\r?\nm=|$)",
            lambda m: m.group(1) + f"b=AS:{max_bitrate}\r\n" + m.group(2),
            sdp,
            flags=re.DOTALL,
        )


__all__ = [
    "SimulcastConfig",
    "SimulcastEncoding",
    "SimulcastManager",
    "CodecNegotiator",
    "SDPFilter",
    "sdp_add_simulcast",
    "sdp_remove_codec",
    "sdp_set_bitrate",
]
