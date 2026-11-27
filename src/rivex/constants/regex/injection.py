"""``rivex.constants.regex.injection`` — XSS / SQL-injection detection patterns.

Backed directly by the native Rust ``RivexInjectionRegex`` PyO3 class.
"""

from __future__ import annotations

from typing import Final

from rivex.constants._rust import RivexInjectionRegex
from rivex.constants.regex.abstraction import IRegexConstant


class InjectionRegex(IRegexConstant):
    """Regex patterns for detecting XSS and SQL injection attempts."""

    XSS_PATTERN: Final[str] = (
        r"(?i)^.*(<script|javascript:|onload=|onerror=|<iframe|<img).*$"
    )
    SQLI_PATTERN: Final[str] = (
        r"(?i)^.*(UNION\s+SELECT|DROP\s+TABLE|ALTER\s+TABLE|DELETE\s+FROM|--|/\*).*$"
    )

    Native = RivexInjectionRegex

    @classmethod
    def has_xss(cls, value: str) -> bool:
        """True if ``value`` contains an XSS marker."""
        return RivexInjectionRegex.has_xss(value)

    @classmethod
    def has_sqli(cls, value: str) -> bool:
        """True if ``value`` contains a SQL injection marker."""
        return RivexInjectionRegex.has_sqli(value)


__all__ = ["InjectionRegex"]
