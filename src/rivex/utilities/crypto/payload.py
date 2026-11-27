"""``rivex.utilities.crypto.payload`` — symmetric Fernet + AES-GCM payload encryption primitive.

Wraps the derive-system-key / unprotect-stored-Fernet-key / Fernet
round-trip that the per-user ``PayloadEncryptionMiddleware`` performs on
every authenticated request. Splitting it out lets the middleware stay
domain-agnostic (the app injects the user-key resolver) while the
crypto lives in one testable helper.
"""

from __future__ import annotations

import base64
from typing import Optional

from rivex.constants.crypto import Encryption
from rivex.utilities.crypto.symmetric import SymmetricCryptoUtility


class PayloadCrypto(SymmetricCryptoUtility):
    """Symmetric Fernet payload encryption with a PBKDF2-derived system key.

    The protected key format stored in the user's row is::

        urlsafe_b64( nonce(12) || aes_gcm_ciphertext( pbkdf2_key, raw_fernet_key ) )

    ``raw_fernet_key`` is the per-user Fernet key used to encrypt /
    decrypt the request + response bodies.

    All knobs (env-var names, defaults, derivation length) live on
    :class:`rivex.constants.crypto.Encryption` so the constants and
    crypto stay in lock-step.
    """

    def __init__(
        self,
        system_salt: str,
        *,
        pbkdf2_salt: bytes = Encryption.DEFAULT_PBKDF2_SALT.encode("utf-8"),
        pbkdf2_iterations: int = Encryption.DEFAULT_PBKDF2_ITERATIONS,
        system_key_len: int = Encryption.DEFAULT_SYSTEM_KEY_LEN,
        env: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__()
        self._system_salt = system_salt
        self._pbkdf2_salt = pbkdf2_salt
        self._pbkdf2_iterations = int(pbkdf2_iterations)
        self._system_key_len = int(system_key_len)

    def derive_system_key(self) -> bytes:
        """Derive the system AES-GCM key from the configured salt + PBKDF2 params."""
        if not self._system_salt:
            raise PayloadCryptoError("system salt not configured")
        return self.pbkdf2_derive(
            password=self._system_salt,
            salt=self._pbkdf2_salt,
            iterations=self._pbkdf2_iterations,
            length=self._system_key_len,
        )

    def protect_fernet_key(self, raw_fernet_key: bytes | str) -> str:
        """AES-GCM-encrypt ``raw_fernet_key`` and return the base64-urlsafe stored form."""
        if isinstance(raw_fernet_key, str):
            raw_fernet_key = raw_fernet_key.encode("utf-8")
        system_key = self.derive_system_key()
        blob = self.aes_gcm_encrypt(system_key, raw_fernet_key)
        return base64.urlsafe_b64encode(blob).decode("ascii")

    def unprotect_fernet_key(self, stored_value: str) -> str:
        """Reverse :meth:`protect_fernet_key` and return the raw Fernet key string."""
        try:
            blob = base64.urlsafe_b64decode(stored_value.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise PayloadCryptoError("stored payload key is not valid base64") from exc
        system_key = self.derive_system_key()
        try:
            plaintext = self.aes_gcm_decrypt(system_key, blob)
        except Exception as exc:
            raise PayloadCryptoError("stored payload key AES-GCM decryption failed") from exc
        try:
            return plaintext.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PayloadCryptoError("stored payload key is not valid UTF-8") from exc


class PayloadCryptoError(RuntimeError):
    """Raised when payload crypto key derivation / unwrapping fails."""


__all__ = ["PayloadCrypto", "PayloadCryptoError"]
