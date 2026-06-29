"""logx SDK adapter — init, shutdown, and contextual child loggers."""

from __future__ import annotations

import dataclasses
import traceback
from typing import TYPE_CHECKING, Any

import logx
from logx import ChildLogger

from abstractions.logger import ILogger
from constants.logger import DEFAULT_REDACT_FIELDS

if TYPE_CHECKING:
    from configs import Settings

_initialized = False


@dataclasses.dataclass(frozen=True, slots=True)
class LoggingSetupOptions:
    """Runtime logging setup — pass explicitly at boot or derive from settings."""

    level: str = "info"
    stdout_enabled: bool = True
    stdout_format: str = "pretty"
    stdout_color: str = "auto"
    log_file: str | None = None
    log_file_gzip: bool = False
    sample_one_in: int = 1
    backpressure: str = "drop"
    caller_info: bool = True
    redact_fields: tuple[str, ...] | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> LoggingSetupOptions:
        log = settings.logging
        return cls(
            level=log.level,
            stdout_enabled=log.log_stdout,
            stdout_format=log.log_stdout_format,
            stdout_color=log.log_stdout_color,
            log_file=log.log_file,
            caller_info=log.log_caller_info,
            sample_one_in=log.log_sample_one_in,
        )

    def with_overrides(self, **overrides: Any) -> LoggingSetupOptions:
        if not overrides:
            return self
        valid = {field.name for field in dataclasses.fields(self)}
        filtered = {key: value for key, value in overrides.items() if key in valid}
        return dataclasses.replace(self, **filtered)


def resolve_logging_setup(
    options: LoggingSetupOptions | None = None,
    /,
    **overrides: Any,
) -> LoggingSetupOptions:
    """Merge explicit setup args on top of provided options or settings defaults."""
    base = options or LoggingSetupOptions()
    return base.with_overrides(**overrides)


class AppLogger:
    """Wraps ``logx.ChildLogger`` with bind/exception helpers."""

    __slots__ = ("_inner",)

    def __init__(self, inner: ChildLogger | None = None, **bound_fields: Any) -> None:
        if inner is not None:
            self._inner = inner
        elif bound_fields:
            self._inner = logx.child(**bound_fields)
        else:
            self._inner = logx.child(service="{{project_slug}}")

    def trace(self, message: str, **fields: Any) -> None:
        self._inner.trace(message, **fields)

    def debug(self, message: str, **fields: Any) -> None:
        self._inner.debug(message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        self._inner.info(message, **fields)

    def warn(self, message: str, **fields: Any) -> None:
        self._inner.warn(message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self._inner.error(message, **fields)

    def child(self, **fields: Any) -> AppLogger:
        return AppLogger(self._inner.child(**fields))

    def bind(self, **fields: Any) -> AppLogger:
        return self.child(**fields)

    def exception(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        **fields: Any,
    ) -> None:
        if exc is not None:
            fields.setdefault("error_type", type(exc).__name__)
            fields.setdefault("error_message", str(exc))
        fields["traceback"] = traceback.format_exc()
        self.error(message, **fields)


def init_logging(
    options: LoggingSetupOptions | None = None,
    /,
    **overrides: Any,
) -> None:
    """Initialize the global logx logger once at application startup."""
    global _initialized
    if _initialized:
        return

    setup = resolve_logging_setup(options, **overrides)
    if setup.stdout_format not in {"pretty", "ndjson"}:
        raise ValueError("stdout_format must be 'pretty' or 'ndjson'")
    if setup.stdout_color not in {"auto", "always", "never"}:
        raise ValueError("stdout_color must be 'auto', 'always', or 'never'")
    if setup.sample_one_in <= 0:
        raise ValueError("sample_one_in must be > 0")

    sinks: list[Any] = []
    if setup.stdout_enabled:
        if setup.stdout_format == "pretty":
            sinks.append(logx.pretty(color=setup.stdout_color))
        else:
            sinks.append(logx.stdout())
    if setup.log_file:
        sinks.append(logx.file(setup.log_file, gzip=setup.log_file_gzip))
    if not sinks:
        sinks.append(logx.pretty(color=setup.stdout_color))

    logx.init(
        sinks,
        level=setup.level,
        backpressure=setup.backpressure,
        sample_one_in=setup.sample_one_in,
        sample_one_in_levels={"error": 1, "warn": 1},
        caller_info=setup.caller_info,
        redact=list(setup.redact_fields or DEFAULT_REDACT_FIELDS),
    )
    _initialized = True


def shutdown_logging() -> None:
    """Flush and shut down logx. Call on application exit."""
    global _initialized
    if _initialized:
        logx.shutdown()
        _initialized = False


def get_logger(**fields: Any) -> AppLogger:
    """Create a child logger with optional bound fields."""
    return AppLogger(service="{{project_slug}}", **fields)


def bind_logger(
    logger: AppLogger | None = None,
    *,
    urn: str = "",
    user_urn: str = "",
    api_name: str = "",
    user_id: str | None = None,
    method: str = "",
    path: str = "",
    component: str = "",
) -> AppLogger:
    """Return a logger with request context fields bound."""
    base = logger or get_logger()
    fields: dict[str, Any] = {"service": "{{project_slug}}"}
    if urn:
        fields["urn"] = urn
        fields["request_id"] = urn
    if user_urn:
        fields["user_urn"] = user_urn
    if api_name:
        fields["api_name"] = api_name
    if user_id:
        fields["user_id"] = user_id
    if method:
        fields["method"] = method
    if path:
        fields["path"] = path
    if component:
        fields["component"] = component
    return base.bind(**fields)


__all__ = [
    "ILogger",
    "AppLogger",
    "LoggingSetupOptions",
    "init_logging",
    "shutdown_logging",
    "get_logger",
    "bind_logger",
    "resolve_logging_setup",
]
