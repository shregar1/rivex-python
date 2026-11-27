"""Encryption algorithms and parameters constants."""

from __future__ import annotations

from typing import Final

from rivex.constants.crypto.abstraction import ICryptoConstant


class Encryption(ICryptoConstant):
    """Supported ciphers plus the env-var names that carry their runtime parameters."""

    AES_256_GCM: Final[str] = "AES-256-GCM"
    AES_256_CBC: Final[str] = "AES-256-CBC"
    AES_128_GCM: Final[str] = "AES-128-GCM"
    AES_128_CBC: Final[str] = "AES-128-CBC"
    CHACHA20_POLY1305: Final[str] = "ChaCha20-Poly1305"
    RSA_OAEP: Final[str] = "RSA-OAEP"
    FERNET: Final[str] = "Fernet"

    SYSTEM_SALT_ENV: Final[str] = "KEY_ENCRYPTION_SYSTEM_SALT"
    PBKDF2_SALT_ENV: Final[str] = "KEY_ENCRYPTION_PBKDF2_SALT"
    PBKDF2_ITERATIONS_ENV: Final[str] = "KEY_ENCRYPTION_PBKDF2_ITERATIONS"
    SYSTEM_KEY_LEN_ENV: Final[str] = "KEY_ENCRYPTION_SYSTEM_KEY_LEN"
    ENCRYPTION_KEY_ENV: Final[str] = "ENCRYPTION_KEY"

    DEFAULT_PBKDF2_SALT: Final[str] = "meridian.payload-key-protection.v1"
    DEFAULT_PBKDF2_ITERATIONS: Final[int] = 200_000
    DEFAULT_SYSTEM_KEY_LEN: Final[int] = 32

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "Encryption"


__all__ = ["Encryption"]
