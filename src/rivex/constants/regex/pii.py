"""``rivex.constants.regex.pii`` — PII detection patterns.

Backed directly by the native Rust ``RivexPiiRegex`` PyO3 class.
"""

from __future__ import annotations

from typing import Final

from rivex.constants._rust import RivexPiiRegex
from rivex.constants.regex.abstraction import IRegexConstant


class PiiRegex(IRegexConstant):
    """Regex patterns for detecting personally identifiable information (PII)."""

    SSN_PATTERN: Final[str] = r"^\d{3}-\d{2}-\d{4}$"
    CARD_PATTERN: Final[str] = r"^\d{13,19}$"

    Native = RivexPiiRegex

    @classmethod
    def is_ssn(cls, value: str) -> bool:
        """True if ``value`` matches the US SSN format (NNN-NN-NNNN)."""
        return RivexPiiRegex.is_ssn(value)

    @classmethod
    def is_card(cls, value: str) -> bool:
        """True if ``value`` looks like a card number (13–19 digits)."""
        return RivexPiiRegex.is_card(value)


__all__ = ["PiiRegex"]
