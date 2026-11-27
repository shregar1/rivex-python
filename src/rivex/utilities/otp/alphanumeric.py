"""Alphanumeric OTP generation (ambiguous glyphs removed)."""

from __future__ import annotations

import re
from typing import Optional

from rivex.utilities.abstraction import LayeredUtility
from rivex.utilities.otp.abstraction import IOTPUtility


class AlphanumericOTPUtility(IOTPUtility, LayeredUtility):
    """Letter + digit OTPs with ``0/O``, ``1/I/L`` removed to avoid ambiguous glyphs."""

    def __init__(
        self,
        length: int = IOTPUtility.ALPHANUMERIC_LENGTH,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.length = int(length)
        self.regex = self.alphabet_regex(self.ALPHANUMERIC_ALPHABET, self.length)

    def generate(self) -> str:
        """Return an alphanumeric OTP of ``self.length`` characters."""
        otp = self._from_alphabet(self.ALPHANUMERIC_ALPHABET, self.length)
        if not self.validate(otp):
            raise ValueError("Generated OTP does not match the expected format")
        return otp

    def validate(self, value: str) -> bool:
        """Return True if ``value`` is an alphanumeric OTP of ``self.length`` characters."""
        return re.fullmatch(self.regex, value or "") is not None

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "AlphanumericOTPUtility"


__all__ = ["AlphanumericOTPUtility"]
