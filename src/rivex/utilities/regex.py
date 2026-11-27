"""``rivex.utilities.regex`` — pre-compile a list of patterns for fast reuse."""

from __future__ import annotations

import re
from typing import List, Sequence

from rivex.utilities.abstraction import LayeredUtility


class RegexUtility(LayeredUtility):
    """Compile and reuse regex patterns across hot paths."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def compile_patterns(cls, patterns: Sequence[str | re.Pattern[str]]) -> List[re.Pattern[str]]:
        """Compile every pattern in ``patterns`` with case-insensitive flag.

        Already-compiled patterns are passed through unchanged; strings
        are wrapped in ``re.compile(p, re.IGNORECASE)``.
        """
        compiled: List[re.Pattern[str]] = []
        for p in patterns:
            if isinstance(p, re.Pattern):
                compiled.append(p)
            elif isinstance(p, str):
                compiled.append(re.compile(p, re.IGNORECASE))
        return compiled

    @property
    def label(self) -> str:
        """Returns the class name."""
        return "RegexUtility"


__all__ = ["RegexUtility"]
