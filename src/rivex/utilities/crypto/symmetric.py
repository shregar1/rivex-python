"""Symmetric encryption, hashing, HMAC, and random-token helpers.

Falls back to Python's stdlib (``hashlib``, ``hmac``, ``secrets``) when
the optional ``rivex_core`` native bindings aren't compiled in, so the
utility is usable on every Python runtime.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any, Final, Optional

from rivex.utilities.abstraction import LayeredUtility
from rivex.utilities.crypto.abstraction import ICryptoUtility


class SymmetricCryptoUtility(ICryptoUtility, LayeredUtility):
    """Fernet / AES-GCM / HMAC / digest / CSPRNG helpers."""

    OTP_DIGITS: Final[str] = "0123456789"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    def sha256(self, data: bytes | str) -> str:
        """Return the SHA-256 hex digest of ``data``."""
        payload = data.encode() if isinstance(data, str) else bytes(data)
        try:
            import rivex_core

            return rivex_core.sha256(payload)
        except (ImportError, AttributeError):
            return hashlib.sha256(payload).hexdigest()

    def hmac_sha256(self, key: bytes | str, data: bytes | str) -> str:
        """Return the HMAC-SHA-256 hex digest of ``data`` keyed by ``key``."""
        k = key.encode() if isinstance(key, str) else bytes(key)
        d = data.encode() if isinstance(data, str) else bytes(d)
        try:
            import rivex_core

            return rivex_core.hmac_sha256(k, d)
        except (ImportError, AttributeError):
            return hmac.new(k, d, hashlib.sha256).hexdigest()

    def hmac_sha256_verify(self, key: bytes | str, data: bytes | str, signature: str) -> bool:
        """Verify an HMAC-SHA-256 hex digest with a timing-safe comparison."""
        k = key.encode() if isinstance(key, str) else bytes(key)
        d = data.encode() if isinstance(data, str) else bytes(d)
        try:
            import rivex_core

            return bool(rivex_core.hmac_sha256_verify(k, d, signature))
        except (ImportError, AttributeError):
            expected = hmac.new(k, d, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, signature)

    def random_token(self, length: int = 32) -> str:
        """Return a URL-safe random token of ``length`` bytes of entropy."""
        return secrets.token_urlsafe(length)

    def random_bytes(self, nbytes: int = 32) -> bytes:
        """Return ``nbytes`` of cryptographically strong random bytes."""
        return secrets.token_bytes(int(nbytes))

    def random_hex(self, nbytes: int = 16) -> str:
        """Return ``nbytes`` of random data encoded as hex."""
        return secrets.token_hex(int(nbytes))

    def generate_OTP(self, length: int = 6) -> str:
        """Return a numeric one-time password of ``length`` digits."""
        return "".join(secrets.choice(self.OTP_DIGITS) for _ in range(int(length)))

    def generate_fernet_key(self) -> str:
        """Return a URL-safe base64-encoded Fernet key (uses ``cryptography`` when available)."""
        try:
            from cryptography.fernet import Fernet

            return Fernet.generate_key().decode()
        except ImportError as exc:
            raise RuntimeError(
                "Fernet key generation requires the 'cryptography' package. "
                "Install it via `pip install cryptography`."
            ) from exc

    def pbkdf2_derive(
        self,
        password: bytes | str,
        salt: bytes | str,
        iterations: int,
        length: int,
    ) -> bytes:
        """Derive a key with PBKDF2-HMAC-SHA256."""
        pwd = password.encode() if isinstance(password, str) else bytes(password)
        s = salt.encode() if isinstance(salt, str) else bytes(salt)
        try:
            import rivex_core

            return bytes(rivex_core.pbkdf2_derive(pwd, s, int(iterations), int(length)))
        except (ImportError, AttributeError):
            return hashlib.pbkdf2_hmac("sha256", pwd, s, int(iterations), int(length))

    def aes_gcm_encrypt(self, key: bytes, plaintext: bytes | str) -> bytes:
        """Encrypt ``plaintext`` with AES-GCM. Returns ``nonce || ciphertext || tag``."""
        try:
            import rivex_core

            payload = plaintext.encode() if isinstance(plaintext, str) else bytes(plaintext)
            return bytes(rivex_core.aes_gcm_encrypt(bytes(key), payload))
        except (ImportError, AttributeError):
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            except ImportError as exc:
                raise RuntimeError(
                    "AES-GCM encryption requires either the Rivex Rust core or "
                    "the 'cryptography' package."
                ) from exc
            nonce = secrets.token_bytes(12)
            ct = AESGCM(bytes(key)).encrypt(nonce, plaintext.encode() if isinstance(plaintext, str) else bytes(plaintext), None)
            return nonce + ct

    def aes_gcm_decrypt(self, key: bytes, ciphertext: bytes) -> bytes:
        """Decrypt an AES-GCM ciphertext blob produced by :meth:`aes_gcm_encrypt`."""
        try:
            import rivex_core

            return bytes(rivex_core.aes_gcm_decrypt(bytes(key), bytes(ciphertext)))
        except (ImportError, AttributeError):
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            except ImportError as exc:
                raise RuntimeError(
                    "AES-GCM decryption requires either the Rivex Rust core or "
                    "the 'cryptography' package."
                ) from exc
            nonce, ct = bytes(ciphertext)[:12], bytes(ciphertext)[12:]
            return AESGCM(bytes(key)).decrypt(nonce, ct, None)

    def fernet_encrypt(self, key: bytes | str, plaintext: bytes | str) -> str:
        """Encrypt ``plaintext`` with Fernet and return a Fernet token string."""
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise RuntimeError(
                "Fernet encryption requires the 'cryptography' package. "
                "Install it via `pip install cryptography`."
            ) from exc
        payload = plaintext.encode() if isinstance(plaintext, str) else bytes(plaintext)
        return Fernet(self._fernet_key(key)).encrypt(payload).decode()

    def fernet_decrypt(self, key: bytes | str, token: bytes | str, ttl: Optional[int] = None) -> bytes:
        """Decrypt a Fernet token produced by :meth:`fernet_encrypt`."""
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise RuntimeError(
                "Fernet decryption requires the 'cryptography' package. "
                "Install it via `pip install cryptography`."
            ) from exc
        raw = token.decode() if isinstance(token, (bytes, bytearray)) else token
        cipher = Fernet(self._fernet_key(key))
        if ttl is None:
            return bytes(cipher.decrypt(raw))
        return bytes(cipher.decrypt_at_time(raw, int(ttl)))

    @staticmethod
    def _fernet_key(key: bytes | str) -> str:
        if isinstance(key, (bytes, bytearray)):
            return key.decode()
        return key

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "SymmetricCryptoUtility"


__all__ = ["SymmetricCryptoUtility"]
