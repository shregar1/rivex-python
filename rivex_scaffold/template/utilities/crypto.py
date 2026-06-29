"""Cryptographic helpers via Rivex ``rivex.crypto``."""

from __future__ import annotations

import secrets

from rivex.crypto import (
    aes_gcm_decrypt,
    aes_gcm_encrypt,
    hmac_sha256,
    hmac_sha256_verify,
    random_bytes,
    random_hex,
    random_token,
    sha256,
)

from abstractions.utility import IUtility


class CryptoUtility(IUtility):
    """Tokens, digests, HMAC, and symmetric encryption."""

    @classmethod
    def name(cls) -> str:
        return "crypto"

    def sha256(self, data: bytes | str) -> str:
        payload = data.encode() if isinstance(data, str) else data
        return sha256(payload)

    def random_token(self, length: int = 32) -> str:
        return random_token(length)

    def random_hex(self, length: int = 32) -> str:
        return random_hex(length)

    def random_bytes(self, length: int = 32) -> bytes:
        return bytes(random_bytes(length))

    def hmac_sha256(self, secret: bytes | str, message: bytes | str) -> str:
        key = secret.encode() if isinstance(secret, str) else secret
        body = message.encode() if isinstance(message, str) else message
        return hmac_sha256(key, body)

    def hmac_sha256_verify(
        self,
        secret: bytes | str,
        message: bytes | str,
        signature: str,
    ) -> bool:
        key = secret.encode() if isinstance(secret, str) else secret
        body = message.encode() if isinstance(message, str) else message
        return hmac_sha256_verify(key, body, signature)

    def aes_gcm_encrypt(self, key: bytes, plaintext: bytes) -> bytes:
        return aes_gcm_encrypt(key, plaintext)

    def aes_gcm_decrypt(self, key: bytes, ciphertext: bytes) -> bytes:
        return aes_gcm_decrypt(key, ciphertext)

    def generate_otp(self, length: int = 6) -> str:
        """Numeric OTP using a secure random token."""
        return "".join(secrets.choice("0123456789") for _ in range(length))
