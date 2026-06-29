"""Error interface — alias for the domain error base type."""

from __future__ import annotations

from typing import Any

from abstractions.context import ContextMixin


class IError(Exception, ContextMixin):
    """Base application error with HTTP mapping."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        **context: Any,
    ) -> None:
        Exception.__init__(self, message)
        ContextMixin.__init__(self, **context)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
