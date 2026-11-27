"""``rivex.auth.data_protection`` — authenticated encryption for sensitive payloads."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

__all__ = ["DataProtector"]


class DataProtector:
    """Provides authenticated encryption (AES-256-GCM) with purpose binding and key rotation backed by rivex-core."""

    def __init__(self, key: bytes, encoding: bool = True) -> None:
        if len(key) != 32:
            raise ValueError("Key must be exactly 32 bytes (256 bits)")
        self._primary_key = key
        self._old_keys: list[bytes] = []
        self._encoding = encoding
        self._rust_protector = None
        try:
            from rivex.native._compat import rc as _rc
            if hasattr(_rc, "RustDataProtector"):
                self._rust_protector = _rc.RustDataProtector(key)
        except Exception:
            pass

    def rotate_key(self, new_key: bytes) -> None:
        """Roll the primary key forward and keep the old one for decryption.

        The current primary key is pushed onto ``_old_keys`` (most-recent
        first) and ``new_key`` becomes the active key. Any underlying
        Rust protector is updated too. ``new_key`` must be exactly 32
        bytes.

        Args:
            new_key: The replacement 32-byte AES key.

        Raises:
            ValueError: When ``new_key`` is not exactly 32 bytes long.
        """
        if len(new_key) != 32:
            raise ValueError("Key must be exactly 32 bytes (256 bits)")
        self._old_keys.append(self._primary_key)
        self._primary_key = new_key
        if self._rust_protector is not None:
            self._rust_protector.rotate_key(new_key)

    def protect_raw(self, plaintext: bytes) -> bytes:
        """Encrypt ``plaintext`` with the primary key and prepend a 12-byte nonce.

        Delegates to the Rust protector when available; otherwise uses
        :class:`AESGCM` directly with a fresh random nonce. The returned
        buffer is ``nonce || ciphertext || tag`` and is safe to feed
        back into :meth:`unprotect_raw`.

        Args:
            plaintext: Arbitrary bytes to encrypt.

        Returns:
            Encrypted bytes including the random nonce and GCM tag.
        """
        if self._rust_protector is not None:
            return bytes(self._rust_protector.protect_raw(plaintext))
        nonce = os.urandom(12)
        aesgcm = AESGCM(self._primary_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def unprotect_raw(self, ciphertext: bytes) -> bytes:
        """Decrypt a buffer produced by :meth:`protect_raw`.

        Tries the primary key first, then each previous key in
        reverse-rotation order so that ciphertexts produced before a
        :meth:`rotate_key` call can still be decrypted. The underlying
        Rust protector short-circuits this whole loop when available.

        Args:
            ciphertext: The encrypted buffer (``nonce || ciphertext ||
                tag``).

        Returns:
            The original plaintext bytes.

        Raises:
            ValueError: When the buffer is too short or no key succeeds
                at authentication.
        """
        if self._rust_protector is not None:
            return bytes(self._rust_protector.unprotect_raw(ciphertext))
        if len(ciphertext) < 28:
            raise ValueError("Decryption failed: payload too short")

        nonce = ciphertext[:12]
        payload = ciphertext[12:]

        for k in [self._primary_key] + list(reversed(self._old_keys)):
            try:
                aesgcm = AESGCM(k)
                return aesgcm.decrypt(nonce, payload, None)
            except Exception:
                continue

        raise ValueError("Decryption failed: invalid key or tampered ciphertext")

    def protect(self, data: Any, purpose: str | None = None) -> str:
        """Encrypt a JSON-serializable value and return a URL-safe token.

        Wraps ``data`` in a small envelope (``{"d": ..., "p": ...}``),
        JSON-encodes it, and produces a :meth:`protect_raw` ciphertext
        which is then base64-url encoded without padding. The optional
        ``purpose`` is bound to the ciphertext and must match on
        :meth:`unprotect`, providing domain separation between tokens.

        Args:
            data: Any JSON-serializable Python value.
            purpose: Optional string to bind the token to a specific
                use case; must be supplied again on :meth:`unprotect`.

        Returns:
            A URL-safe string token suitable for cookies, query params,
            or other transports that dislike raw binary.
        """
        if self._rust_protector is not None:
            data_json = json.dumps(data)
            return self._rust_protector.protect(data_json, purpose)

        payload = {"d": data}
        if purpose is not None:
            payload["p"] = purpose

        json_bytes = json.dumps(payload).encode("utf-8")
        raw = self.protect_raw(json_bytes)
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    def unprotect(self, token: str, purpose: str | None = None) -> Any:
        """Reverse of :meth:`protect`; returns the original value or raises.

        URL-safe base64 decodes the token (re-adding any stripped
        padding), decrypts the bytes via :meth:`unprotect_raw`, JSON
        parses the payload, and verifies that any ``purpose`` embedded
        in the payload matches the supplied ``purpose``.

        Args:
            token: The token produced by :meth:`protect`.
            purpose: Optional purpose string that must match the one
                used at encryption time.

        Returns:
            The original Python value passed to :meth:`protect`.

        Raises:
            ValueError: When the token is not valid base64, the
                decryption fails, or the purpose does not match.
        """
        if self._rust_protector is not None:
            json_str = self._rust_protector.unprotect(token, purpose)
            return json.loads(json_str)

        try:
            padded = token + "=" * (-len(token) % 4)
            ciphertext = base64.urlsafe_b64decode(padded.encode("utf-8"))
        except Exception:
            raise ValueError("Decryption failed: invalid base64 encoding")

        plaintext = self.unprotect_raw(ciphertext)
        payload = json.loads(plaintext.decode("utf-8"))

        if purpose is not None and payload.get("p") != purpose:
            raise ValueError(f"Purpose mismatch: expected {purpose!r}, got {payload.get('p')!r}")

        return payload["d"]
