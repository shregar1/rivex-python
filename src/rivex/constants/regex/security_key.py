"""``rivex.constants.regex.security_key`` — API key / secret pattern matcher.

Backed directly by the native Rust ``RivexSecurityKeyRegex`` PyO3 class.
"""

from __future__ import annotations

from typing import Final

from rivex.constants._rust import RivexSecurityKeyRegex
from rivex.constants.regex.abstraction import IRegexConstant


class SecurityKeyRegex(IRegexConstant):
    """Regex patterns for detecting API keys, secrets, and tokens."""

    DEFAULT_KEY_NAMES: Final[list[str]] = RivexSecurityKeyRegex.default_key_names()
    DEFAULT_VALUE_PATTERNS: Final[list[str]] = RivexSecurityKeyRegex.default_value_patterns()

    Native = RivexSecurityKeyRegex

    @classmethod
    def is_sensitive_key(cls, name: str) -> bool:
        """True if ``name`` looks like a parameter that carries a secret."""
        return RivexSecurityKeyRegex.is_sensitive_key(name)

    @classmethod
    def matches_value(cls, value: str) -> bool:
        """True if ``value`` matches one of the known secret value patterns."""
        return RivexSecurityKeyRegex.matches_value(value)


__all__ = ["SecurityKeyRegex"]
