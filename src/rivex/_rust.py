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
    """Build a stub for a ``rivex_core`` symbol that the installed wheel does not export.

    The returned callable raises ``NotImplementedError`` only when it is
    actually invoked, so the rest of the package remains importable on
    older builds that predate a given validator or hashing helper. The
    stub is renamed to ``name`` so tracebacks surface the missing symbol
    in a recognizable form.

    Args:
        name: Dotted name of the missing ``rivex_core`` attribute (e.g.
            ``"hash_argon2"``).

    Returns:
        A zero-argument callable that raises ``NotImplementedError``
        when called.
    """
    def _stub(*_args, **_kwargs):
        """Reject the call with a message identifying the missing ``rivex_core`` symbol.

        Args:
            *_args: Positional arguments forwarded from the caller —
                ignored because the underlying function is unavailable.
            **_kwargs: Keyword arguments forwarded from the caller —
                also ignored.

        Raises:
            NotImplementedError: Always. The message points at the
                missing symbol and the build command needed to add it.
        """
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
