"""Asymmetric signing helpers backed by Rivex-core Ed25519 (ed25519-dalek)."""

from __future__ import annotations

from typing import Any

from rivex.utilities.abstraction import LayeredUtility
from rivex.utilities.crypto.abstraction import ICryptoUtility


class AsymmetricCryptoUtility(ICryptoUtility, LayeredUtility):
    """Ed25519 keygen / sign / verify via the Rivex Rust core.

    Falls back to ``cryptography`` when the Rust extension isn't built
    so the utility is usable on every Python runtime.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    def generate_ed25519_keypair(self) -> tuple[bytes, bytes]:
        """Return a raw Ed25519 ``(private_key, public_key)`` pair."""
        try:
            import rivex_core

            priv, pub = rivex_core.ed25519_keygen()
            return bytes(priv), bytes(pub)
        except (ImportError, AttributeError):
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

                priv = Ed25519PrivateKey.generate()
                pub = priv.public_key()
                from cryptography.hazmat.primitives import serialization

                return (
                    priv.private_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PrivateFormat.Raw,
                        encryption_algorithm=serialization.NoEncryption(),
                    ),
                    pub.public_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PublicFormat.Raw,
                    ),
                )
            except ImportError as exc:
                raise RuntimeError(
                    "Ed25519 keygen requires either the Rivex Rust core or "
                    "the 'cryptography' package."
                ) from exc

    def ed25519_sign(self, private_key: bytes, data: bytes | str) -> bytes:
        """Sign ``data`` with an Ed25519 private key."""
        payload = data.encode() if isinstance(data, str) else bytes(data)
        try:
            import rivex_core

            return bytes(rivex_core.ed25519_sign(bytes(private_key), payload))
        except (ImportError, AttributeError):
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                from cryptography.hazmat.primitives import serialization

                priv = Ed25519PrivateKey.from_private_bytes(bytes(private_key))
                return priv.sign(payload)
            except ImportError as exc:
                raise RuntimeError(
                    "Ed25519 sign requires either the Rivex Rust core or "
                    "the 'cryptography' package."
                ) from exc

    def ed25519_verify(self, public_key: bytes, data: bytes | str, signature: bytes) -> bool:
        """Verify an Ed25519 signature. Returns False on mismatch (never raises)."""
        payload = data.encode() if isinstance(data, str) else bytes(data)
        try:
            import rivex_core

            return bool(rivex_core.ed25519_verify(bytes(public_key), payload, bytes(signature)))
        except (ImportError, AttributeError):
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                from cryptography.exceptions import InvalidSignature

                pub = Ed25519PublicKey.from_public_bytes(bytes(public_key))
            except ImportError:
                return False
            try:
                pub.verify(bytes(signature), payload)
                return True
            except InvalidSignature:
                return False

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "AsymmetricCryptoUtility"


__all__ = ["AsymmetricCryptoUtility"]
