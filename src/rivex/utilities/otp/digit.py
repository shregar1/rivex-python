"""Numeric digit OTP generation."""

from __future__ import annotations

import re

from rivex.utilities.abstraction import LayeredUtility
from rivex.utilities.otp.abstraction import IOTPUtility


class DigitOTPUtility(IOTPUtility, LayeredUtility):
    """Numeric-only one-time passwords."""

    def __init__(
        self,
        length: int = IOTPUtility.DIGIT_LENGTH,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.length = int(length)
        self.regex = self.alphabet_regex(self.DIGIT_ALPHABET, self.length)

    def generate(self) -> str:
        """Return a numeric OTP of ``self.length`` digits."""
        otp = self._from_alphabet(self.DIGIT_ALPHABET, self.length)
        if not self.validate(otp):
            raise ValueError("Generated OTP does not match the expected format")
        return otp

    def validate(self, value: str) -> bool:
        """Return True if ``value`` is a numeric OTP of ``self.length`` digits."""
        return re.fullmatch(self.regex, value or "") is not None

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "DigitOTPUtility"


__all__ = ["DigitOTPUtility"]
