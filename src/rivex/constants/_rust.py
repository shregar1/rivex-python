"""Native Rust core bindings bridge for ``rivex.constants``.

Directly exposes PyO3 native Rust classes from ``rivex_core``.
"""

from __future__ import annotations

from rivex_core import (
    RivexErrorCode,
    RivexHeader,
    RivexInjectionRegex,
    RivexIRegexConstant,
    RivexMediaType,
    RivexPiiRegex,
    RivexSecurityKeyRegex,
    RustRegex,
)

try:
    from rivex_core import RivexHTTPMethod
except ImportError:
    try:
        # Older rivex_core spelled it RivexHttpMethod (same native enum incl. QUERY).
        from rivex_core import RivexHttpMethod as RivexHTTPMethod
    except ImportError:
        # Last resort: stdlib http.HTTPMethod (GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS).
        from http import HTTPMethod as RivexHTTPMethod

__all__ = [
    "RivexHTTPMethod",
    "RivexMediaType",
    "RivexHeader",
    "RivexErrorCode",
    "RivexIRegexConstant",
    "RivexSecurityKeyRegex",
    "RivexPiiRegex",
    "RivexInjectionRegex",
    "RustRegex",
]
