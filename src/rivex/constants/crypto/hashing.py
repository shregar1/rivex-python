"""``rivex.constants.crypto.hashing`` — password + message hashing algorithm constants."""

from __future__ import annotations

from typing import Final

from rivex.constants.crypto.abstraction import ICryptoConstant


class Hashing(ICryptoConstant):
    """Supported hashing algorithms and HMAC variants."""

    ARGON2: Final[str] = "argon2"
    BCRYPT: Final[str] = "bcrypt"
    HMAC_SHA256: Final[str] = "sha256"
    HMAC_SHA512: Final[str] = "sha512"
    HMAC_MD5: Final[str] = "md5"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "Hashing"


__all__ = ["Hashing"]
