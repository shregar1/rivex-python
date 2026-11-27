"""``rivex.constants.regex.abstraction`` — base regex constant interface.

Backed directly by the native Rust ``RivexIRegexConstant`` PyO3 class.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Union

from rivex.constants._rust import RivexIRegexConstant
from rivex.constants.abstraction import IConstant


class IRegexConstant(IConstant):
    """Base interface for Rivex regex constant groups."""

    @classmethod
    def compile_patterns(
        cls,
        patterns: Sequence[Union[str, "re.Pattern[str]"]],
    ) -> list:
        """Compile a list of pattern strings into RustRegex objects."""
        str_patterns = [p if isinstance(p, str) else p.pattern for p in patterns]
        return RivexIRegexConstant.compile_patterns(str_patterns)


__all__ = ["IRegexConstant"]
