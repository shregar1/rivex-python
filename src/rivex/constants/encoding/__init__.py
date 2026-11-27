"""``rivex.constants.encoding`` — text encodings, content encodings, and hash algorithm names."""

from __future__ import annotations

from typing import Final

from rivex.constants.abstraction import IConstant


class Encoding(IConstant):
    """Canonical text / wire encodings."""

    UTF_8: Final[str] = "utf-8"
    UTF_16: Final[str] = "utf-16"
    UTF_32: Final[str] = "utf-32"
    ASCII: Final[str] = "ascii"
    LATIN_1: Final[str] = "latin-1"
    ISO_8859_1: Final[str] = "iso-8859-1"
    BASE64: Final[str] = "base64"
    HEX: Final[str] = "hex"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "Encoding"


class ContentEncoding(IConstant):
    """HTTP ``Content-Encoding`` values."""

    GZIP: Final[str] = "gzip"
    DEFLATE: Final[str] = "deflate"
    BR: Final[str] = "br"
    IDENTITY: Final[str] = "identity"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "ContentEncoding"


class HashAlgorithm(IConstant):
    """Hash algorithm identifiers recognised across the framework."""

    SHA256: Final[str] = "sha256"
    SHA512: Final[str] = "sha512"
    SHA1: Final[str] = "sha1"
    MD5: Final[str] = "md5"
    BCRYPT: Final[str] = "bcrypt"
    ARGON2: Final[str] = "argon2"

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "HashAlgorithm"


__all__ = ["Encoding", "ContentEncoding", "HashAlgorithm"]
