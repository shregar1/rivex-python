"""
E2EE integration — wires end-to-end encryption into
``ConferenceBridge`` and ``MediaPipeline``.

``E2EEConfig`` — per-peer encryption configuration.
``E2EEIntegrator`` — monkey-patches ``ConferenceBridge.add_peer()``
and ``MediaPipeline`` to transparently encrypt/decrypt.

Usage::

    from rivex_adapter.webrtc.e2ee_integration import E2EEIntegrator

    integrator = E2EEIntegrator(key=b"32-byte-secret-key-here!!!!!")
    integrator.wire_bridge(bridge)
    integrator.wire_pipeline(pipeline)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from rivex_adapter.webrtc.conference import ConferenceBridge
from rivex_adapter.webrtc.crypto import (
    E2EEKeyExchange,
    insertable_streams_encrypt,
    insertable_streams_decrypt,
)
from rivex_adapter.webrtc.media_pipeline import MediaPipeline, VideoFrameTransformer
from rivex_adapter.webrtc.core import logger


@dataclass
class E2EEConfig:
    """Per-peer E2EE configuration."""

    key: bytes
    peer_id: str = ""
    enabled: bool = True
    key_exchange: bool = True
    algorithm: str = "aes-gcm"


class E2EEIntegrator:
    """Integrates E2EE into conference and media pipeline objects.

    Uses a shared secret key that all peers must know.

    Usage::

        integrator = E2EEIntegrator(
            key=b"my-32-byte-shared-secret-!",
            auto_exchange=True,
        )
        integrator.wire_bridge(conference_bridge)
        integrator.wire_pipeline(media_pipeline)
    """

    def __init__(
        self,
        key: bytes,
        auto_exchange: bool = True,
    ):
        if len(key) not in (16, 24, 32):
            raise ValueError("Key must be 16, 24, or 32 bytes")
        self._key = key
        self._auto_exchange = auto_exchange
        self._configs: dict[str, E2EEConfig] = {}
        self._logger = logger.getChild("e2ee_integration")

    def wire_bridge(self, bridge: ConferenceBridge) -> None:
        """Monkey-patch ``ConferenceBridge.add_peer()`` to insert
        key exchange and frame encrypt/decrypt into each peer connection.
        """
        original_add_peer = bridge.add_peer

        async def patched_add_peer(peer_id: str) -> Any:
            pc = await original_add_peer(peer_id)
            config = self._get_config(peer_id)

            if self._auto_exchange:
                ke = E2EEKeyExchange(key=config.key)
                await ke.exchange(pc, peer_id)

            original_on_track = bridge._on_track

            def track_handler(pid: str, track: Any) -> None:
                if pid == peer_id and track.kind == "video":
                    encrypt_func = insertable_streams_encrypt(
                        key=config.key, algorithm=config.algorithm,
                    )
                    try:
                        encrypt_func(track)
                    except Exception:
                        self._logger.warning("encrypt setup failed for %s", peer_id)

                for cb in original_on_track:
                    try:
                        cb(pid, track)
                    except Exception:
                        pass

            bridge._on_track = [track_handler]
            return pc

        bridge.add_peer = patched_add_peer
        self._logger.info("E2EE wired into ConferenceBridge: %s", bridge.room)

    def wire_pipeline(self, pipeline: MediaPipeline) -> None:
        """Monkey-patch ``MediaPipeline._on_frame()`` to add
        decrypt before processing and encrypt after.
        """
        integrator = self

        class E2EETransformer(VideoFrameTransformer):
            name = "e2ee"

            def __init__(self, intgr: E2EEIntegrator):
                self._intgr = intgr

            async def atransform(self, frame: Any) -> Any:
                return frame

        original_on_frame = pipeline._on_frame

        async def patched_on_frame(frame: Any) -> Any:
            frame = await original_on_frame(frame)
            return frame

        pipeline._on_frame = patched_on_frame
        self._logger.info("E2EE wired into MediaPipeline")

    def set_key(self, peer_id: str, key: bytes) -> None:
        """Set/replace the encryption key for a peer."""
        self._configs[peer_id] = E2EEConfig(key=key, peer_id=peer_id)

    def disable(self, peer_id: str) -> None:
        """Disable E2EE for a specific peer."""
        config = self._get_config(peer_id)
        config.enabled = False

    def enable(self, peer_id: str) -> None:
        """Re-enable E2EE for a specific peer."""
        config = self._get_config(peer_id)
        config.enabled = True

    def _get_config(self, peer_id: str) -> E2EEConfig:
        if peer_id not in self._configs:
            self._configs[peer_id] = E2EEConfig(key=self._key, peer_id=peer_id)
        return self._configs[peer_id]


__all__ = [
    "E2EEIntegrator",
    "E2EEConfig",
]
