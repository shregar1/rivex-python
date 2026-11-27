"""``rivex.utilities.otp.abstraction`` — shared base for OTP utilities."""

from __future__ import annotations

import re
import secrets
import string
from abc import abstractmethod
from typing import Optional

from rivex.utilities.abstraction import LayeredUtility


class IOTPUtility(LayeredUtility):
    """Base class for one-time password generators."""

    DIGIT_ALPHABET: str = string.digits
    """Digits only (``"0123456789"``)."""

    ALPHABETIC_ALPHABET: str = string.ascii_uppercase
    """Uppercase letters (``A-Z``) — case-insensitive at validate-time anyway."""

    ALPHANUMERIC_ALPHABET: str = (
        "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    )
    """Letters + digits with ``0/O``, ``1/I/L`` removed to avoid ambiguous glyphs."""

    HEX_ALPHABET: str = "0123456789abcdef"

    DIGIT_LENGTH: int = 6
    ALPHABETIC_LENGTH: int = 8
    ALPHANUMERIC_LENGTH: int = 8
    HEX_LENGTH: int = 8
    PASSPHRASE_WORD_COUNT: int = 4
    PASSPHRASE_SEPARATOR: str = "-"

    # Small built-in word list for passphrase generation. 32 short, common
    # English words — enough entropy for a memorable OTP without pulling in
    # a multi-megabyte wordlist. Override via ``words=`` in subclasses.
    WORDS: tuple[str, ...] = (
        "apple", "bridge", "crane", "delta", "ember", "frost", "glade", "harbor",
        "ivory", "jolly", "knack", "lemon", "maple", "noble", "ocean", "piano",
        "quilt", "river", "stone", "tiger", "umbra", "vivid", "whale", "xenon",
        "yacht", "zesty", "amber", "blaze", "coral", "drift", "eagle", "fjord",
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    @staticmethod
    def alphabet_regex(alphabet: str, length: int) -> str:
        """Return a ``re.fullmatch``-friendly pattern for the fixed-length OTP."""
        return "^[" + alphabet + "]{" + str(length) + "}$"

    @staticmethod
    def passphrase_regex(word_count: int, separator: str) -> str:
        """Return a regex for ``word_count`` words joined by ``separator``."""
        return r"^([A-Za-z]+" + re.escape(separator) + r"){" + str(word_count - 1) + r"}[A-Za-z]+$"

    def _from_alphabet(self, alphabet: str, length: int) -> str:
        if length < 1:
            raise ValueError("OTP length must be at least 1")
        if not alphabet:
            raise ValueError("OTP alphabet must not be empty")
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @abstractmethod
    def generate(self) -> str:
        """Generate an OTP in this utility's format."""

    @abstractmethod
    def validate(self, value: str) -> bool:
        """Return True if ``value`` matches this utility's OTP format."""

    @property
    @abstractmethod
    def label(self) -> str:
        """Returns the class name."""
        raise NotImplementedError

