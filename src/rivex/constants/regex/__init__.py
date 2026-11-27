"""``rivex.constants.regex`` — regex pattern package."""

from __future__ import annotations

from rivex.constants.regex.abstraction import IRegexConstant
from rivex.constants.regex.injection import InjectionRegex
from rivex.constants.regex.patterns import Regex
from rivex.constants.regex.pii import PiiRegex
from rivex.constants.regex.security_key import SecurityKeyRegex

__all__ = [
    "IRegexConstant",
    "InjectionRegex",
    "PiiRegex",
    "Regex",
    "SecurityKeyRegex",
]
