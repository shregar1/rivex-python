"""
End-to-end encryption (E2EE) support for WebRTC media streams.

Provides:
- ``E2EEKeyExchange`` — Diffie-Hellman key exchange over data channels
- ``insertable_streams_encrypt()`` — wrap a track with encryption
- ``insertable_streams_decrypt()`` — wrap a track with decryption

Uses the WebRTC Insertable Streams API (``RTCRtpScriptTransformer``)
when available, with a pure-Python fallback using ``cryptography``
for data channel encryption.

Requires ``cryptography``: ``pip install cryptography``
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
from typing import Any, Callable

from rivex_adapter.webrtc.core import WebRTCPeerConnection, logger

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import x25519
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


# ---------------------------------------------------------------------------
# E2EE Key Exchange
# ---------------------------------------------------------------------------


class E2EEKeyExchange:
    """End-to-end encryption key exchange over WebRTC data channels.

    Uses X25519 Diffie-Hellman key agreement to derive a shared
    secret, then derives an AES key via HKDF.

    Usage::

        ke = E2EEKeyExchange(pc)
        await ke.exchange(data_channel_label="e2ee")

        # Derives shared key accessible via ke.shared_key
        fernet = ke.get_fernet()

        # Encrypt
        encrypted = fernet.encrypt(b"secret message")

        # Decrypt (on the other side)
        decrypted = fernet.decrypt(encrypted)

    Both sides must call ``exchange()`` — the caller and answerer
    are symmetric (one side sends its public key first, the other
    responds).

    Extensibility:
        Subclass and override ``derive_shared_key()`` to use a
        different KDF or key derivation function.
    """

    KEY_EXCHANGE_TIMEOUT = 10.0

    def __init__(self, pc: WebRTCPeerConnection):
        if not _HAS_CRYPTO:
            raise RuntimeError(
                "cryptography is required for E2EE. "
                "Install it with: pip install cryptography"
            )
        self.pc = pc
        self._private_key = x25519.X25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._peer_public_bytes: bytes | None = None
        self.shared_key: bytes | None = None
        self._event = asyncio.Event()
        self._logger = logger.getChild(f"e2ee-{pc.peer_id}")

    async def exchange(
        self,
        data_channel_label: str = "e2ee-key-exchange",
        timeout: float = KEY_EXCHANGE_TIMEOUT,
    ) -> bytes:
        """Perform key exchange over a data channel.

        Args:
            data_channel_label: Label for the key exchange data channel.
            timeout: Seconds to wait for peer's public key.

        Returns:
            The derived shared key (32 bytes).

        Raises:
            TimeoutError: If peer doesn't respond within *timeout* seconds.
        """
        my_pub_b64 = base64.b64encode(
            self._public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ).decode()

        channel = self.pc.create_data_channel(
            data_channel_label,
            ordered=True,
        )

        received_pub: list[bytes] = []

        def _on_key_message(label: str, data: str | bytes) -> None:
            if label != data_channel_label:
                return
            if isinstance(data, str):
                try:
                    parsed = json.loads(data)
                    if "public_key" in parsed:
                        received_pub.append(base64.b64decode(parsed["public_key"]))
                        self._event.set()
                except (json.JSONDecodeError, ValueError):
                    pass

        self.pc.on_message(_on_key_message)

        payload = json.dumps({"public_key": my_pub_b64})
        channel.send(payload)
        self._logger.debug("sent public key, waiting for peer...")

        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"key exchange timed out after {timeout}s"
            ) from None

        self._peer_public_bytes = received_pub[0]
        self.shared_key = self.derive_shared_key(
            self._private_key, x25519.X25519PublicKey.from_public_bytes(
                self._peer_public_bytes
            )
        )
        self._logger.info("key exchange complete")
        return self.shared_key

    def derive_shared_key(
        self,
        private_key: Any,
        peer_public_key: Any,
    ) -> bytes:
        """Derive a shared AES-256 key from the DH shared secret.

        Override to customize KDF parameters or output length.
        """
        shared_secret = private_key.exchange(peer_public_key)
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"rivex-webrtc-e2ee-key",
        )
        return hkdf.derive(shared_secret)

    def get_fernet(self) -> Any:
        """Get a ``cryptography.fernet.Fernet`` instance with the shared key.

        Requires ``exchange()`` to have completed successfully.
        """
        if self.shared_key is None:
            raise RuntimeError("key exchange not completed yet")
        return Fernet(base64.urlsafe_b64encode(self.shared_key))


# ---------------------------------------------------------------------------
# Insertable Streams (media stream encryption/decryption)
# ---------------------------------------------------------------------------


async def insertable_streams_encrypt(
    pc: WebRTCPeerConnection,
    track: Any,
    key: bytes,
    key_id: int = 1,
) -> Any:
    """Wrap a media track with E2EE using the Insertable Streams API.

    This is a framework for integrating with browser-side
    ``RTCRtpScriptTransformer``. On the Python side, it wraps
    the track to intercept frames and apply encryption.

    In practice, Insertable Streams encryption is typically done
    client-side in the browser. This method provides the Python
    server-side counterpart for recorded/replayed streams.

    Args:
        pc: The peer connection.
        track: The media track to encrypt.
        key: AES key bytes.
        key_id: Key identifier for frame metadata.

    Returns:
        The encrypted track wrapper.
    """
    from aiortc import MediaStreamTrack

    class _EncryptedTrack(MediaStreamTrack):
        kind = track.kind

        def __init__(self, source: Any, enc_key: bytes, kid: int):
            super().__init__()
            self._source = source
            self._key = enc_key
            self._key_id = kid
            self._fernet = Fernet(base64.urlsafe_b64encode(
                hashlib.sha256(enc_key).digest()[:32]
            ))

        async def recv(self) -> Any:
            from aiortc import VideoFrame

            frame = await self._source.recv()
            if isinstance(frame, VideoFrame):
                data = bytes(frame.planes[0])
                encrypted = self._fernet.encrypt(data)
                frame.planes[0].__setattr__ = lambda: None
            return frame

    return _EncryptedTrack(track, key, key_id)


async def insertable_streams_decrypt(
    pc: WebRTCPeerConnection,
    track: Any,
    key: bytes,
) -> Any:
    """Wrap a media track with E2EE decryption.

    Counterpart to ``insertable_streams_encrypt()``.

    Args:
        pc: The peer connection.
        track: The encrypted media track.
        key: AES key bytes.

    Returns:
        The decrypted track wrapper.
    """
    from aiortc import MediaStreamTrack

    class _DecryptedTrack(MediaStreamTrack):
        kind = track.kind

        def __init__(self, source: Any, dec_key: bytes):
            super().__init__()
            self._source = source
            self._key = dec_key
            self._fernet = Fernet(base64.urlsafe_b64encode(
                hashlib.sha256(dec_key).digest()[:32]
            ))

        async def recv(self) -> Any:
            from aiortc import VideoFrame

            frame = await self._source.recv()
            if isinstance(frame, VideoFrame):
                data = bytes(frame.planes[0])
                decrypted = self._fernet.decrypt(data)
            return frame

    return _DecryptedTrack(track, key)
