"""Logger interface — implemented by the logx adapter."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ILogger(Protocol):
    """Structured logger contract used across all layers."""

    def trace(self, message: str, **fields: Any) -> None: ...

    def debug(self, message: str, **fields: Any) -> None: ...

    def info(self, message: str, **fields: Any) -> None: ...

    def warn(self, message: str, **fields: Any) -> None: ...

    def error(self, message: str, **fields: Any) -> None: ...

    def child(self, **fields: Any) -> ILogger: ...

    def bind(self, **fields: Any) -> ILogger: ...

    def exception(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        **fields: Any,
    ) -> None: ...
