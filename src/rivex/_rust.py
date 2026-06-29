"""Rust-accelerated password hashing and validators from ``rivex_core``.

If the installed ``rivex_core`` extension doesn't ship a given function (e.g.
the installed wheel predates a new validator), we substitute a placeholder
that raises only when the function is actually called. This keeps the rest
of the package importable on older builds.
"""

from __future__ import annotations

import rivex_core as _rc

_EXPORTS = (
    "hash_password",
    "verify_password",
    "hash_bcrypt",
    "hash_argon2",
    "validate_email",
    "validate_url",
    "validate_ip",
    "validate_uuid",
    "validate_phone",
    "validate_json_schema",
    "is_ascii",
    "validate_iban",
    "format_iban",
    "luhn_check",
    "sanitize_html",
    "strip_html_tags",
)


def _missing(name: str):
    def _stub(*_args, **_kwargs):
        raise NotImplementedError(
            f"rivex_core.{name} is not available in the installed extension. "
            f"Rebuild rivex-core (maturin develop --release) to enable it."
        )

    _stub.__name__ = name
    return _stub


_g = globals()
for _name in _EXPORTS:
    _g[_name] = getattr(_rc, _name, None) or _missing(_name)  # type: ignore[assignment]

__all__ = list(_EXPORTS)
