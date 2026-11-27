"""Passphrase OTP generation — random words joined by a separator."""

from __future__ import annotations

import re
import secrets
from typing import Optional

from rivex.utilities.abstraction import LayeredUtility
from rivex.utilities.otp.abstraction import IOTPUtility


class PassphraseOTPUtility(IOTPUtility, LayeredUtility):
    """Generates space-free passphrase OTPs from a small built-in word list."""

    def __init__(
        self,
        word_count: int = IOTPUtility.PASSPHRASE_WORD_COUNT,
        separator: str = IOTPUtility.PASSPHRASE_SEPARATOR,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.word_count = int(word_count)
        self.separator = separator
        self.regex = self.passphrase_regex(word_count=self.word_count, separator=self.separator)

    def generate(self) -> str:
        """Return ``self.word_count`` random words joined by ``self.separator``."""
        if self.word_count < 1:
            raise ValueError("Passphrase word count must be at least 1")
        words = tuple(secrets.choice(self.WORDS) for _ in range(self.word_count))
        otp = self.separator.join(words)
        if not self.validate(otp):
            raise ValueError("Generated OTP does not match the expected format")
        return otp

    def validate(self, value: str) -> bool:
        """Return True if ``value`` is a passphrase OTP for this utility's word list."""
        return re.fullmatch(self.regex, value or "") is not None

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "PassphraseOTPUtility"


__all__ = ["PassphraseOTPUtility"]
