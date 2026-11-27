"""``rivex.utilities.otp`` — one-time password (OTP) generation and validation utilities.

Subpackage overview:

* :class:`DigitOTPUtility`       — numeric OTPs (``0123456789``)
* :class:`AlphabeticOTPUtility`  — letter-only OTPs
* :class:`AlphanumericOTPUtility`— letters + digits, ambiguous glyphs removed
* :class:`HexOTPUtility`         — hex OTPs (``0-9a-f``)
* :class:`PassphraseOTPUtility`  — space-free passphrase OTPs from a small word list

All five expose the same interface (:meth:`generate`, :meth:`validate`,
:attr:`length`, :attr:`regex`) so they can be substituted freely.
"""

from __future__ import annotations

from rivex.utilities.otp.abstraction import IOTPUtility
from rivex.utilities.otp.alphabetic import AlphabeticOTPUtility
from rivex.utilities.otp.alphanumeric import AlphanumericOTPUtility
from rivex.utilities.otp.digit import DigitOTPUtility
from rivex.utilities.otp.hex import HexOTPUtility
from rivex.utilities.otp.passphrase import PassphraseOTPUtility

__all__ = [
    "IOTPUtility",
    "DigitOTPUtility",
    "AlphabeticOTPUtility",
    "AlphanumericOTPUtility",
    "HexOTPUtility",
    "PassphraseOTPUtility",
]
