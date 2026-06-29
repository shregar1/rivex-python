"""Structured start/complete/fail timing logs for async and sync callables."""

from __future__ import annotations

import functools
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypeVar, cast

from constants.logger import (
    CONTROLLER_COMPLETED,
    CONTROLLER_FAILED,
    CONTROLLER_STARTED,
    DB_QUERY_SLOW,
    REPOSITORY_COMPLETED,
    REPOSITORY_FAILED,
    REPOSITORY_STARTED,
    REQUEST_COMPLETED,
    REQUEST_FAILED,
    REQUEST_STARTED,
    SERVICE_COMPLETED,
    SERVICE_FAILED,
    SERVICE_STARTED,
    UTILITY_COMPLETED,
    UTILITY_FAILED,
    UTILITY_STARTED,
)
from utilities.request_timing import record_layer_timing

Layer = Literal["repository", "service", "controller", "utility", "http"]

_LAYER_CONFIG: dict[Layer, dict[str, Any]] = {
    "repository": {
        "started_code": REPOSITORY_STARTED,
        "completed_code": REPOSITORY_COMPLETED,
        "failed_code": REPOSITORY_FAILED,
        "started_message": "Repository operation started",
        "completed_message": "Repository operation completed",
        "failed_message": "Repository operation failed",
        "slow_code": DB_QUERY_SLOW,
        "slow_message": "Slow database query",
        "domain_error_level": "error",
    },
    "service": {
        "started_code": SERVICE_STARTED,
        "completed_code": SERVICE_COMPLETED,
        "failed_code": SERVICE_FAILED,
        "started_message": "Service execution started",
        "completed_message": "Service execution completed",
        "failed_message": "Service execution failed",
        "domain_error_level": "warn",
    },
    "controller": {
        "started_code": CONTROLLER_STARTED,
        "completed_code": CONTROLLER_COMPLETED,
        "failed_code": CONTROLLER_FAILED,
        "started_message": "Controller handler started",
        "completed_message": "Controller handler completed",
        "failed_message": "Controller handler failed",
        "domain_error_level": "warn",
    },
    "utility": {
        "started_code": UTILITY_STARTED,
        "completed_code": UTILITY_COMPLETED,
        "failed_code": UTILITY_FAILED,
        "started_message": "Utility operation started",
        "completed_message": "Utility operation completed",
        "failed_message": "Utility operation failed",
        "domain_error_level": "error",
    },
    "http": {
        "started_code": REQUEST_STARTED,
        "completed_code": REQUEST_COMPLETED,
        "failed_code": REQUEST_FAILED,
        "started_message": "HTTP request started",
        "completed_message": "HTTP request completed",
        "failed_message": "HTTP request failed",
        "domain_error_level": "error",
    },
}

F = TypeVar("F", bound=Callable[..., Any])


class LoggerContext:
    """Minimal object for :func:`run_timer` when only a logger is available."""

    __slots__ = ("logger",)

    def __init__(self, logger: Any) -> None:
        self.logger = logger


def _result_count(result: Any) -> int | None:
    if isinstance(result, bool):
        return int(result)
    if isinstance(result, int):
        return result
    if result is None:
        return 0
    try:
        return len(result)
    except TypeError:
        return None


def _repository_fields(instance: Any, operation: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "repository": instance.__class__.__name__,
        "model": instance._model().__name__,
        "operation": operation,
    }
    if operation in {"find_by_id", "delete"} and len(args) > 1:
        fields["entity_id"] = args[1]
    elif operation == "find_by_urn" and len(args) > 1:
        fields["entity_id"] = str(args[1])
    elif operation in {"create", "update"} and len(args) > 1:
        fields["entity_id"] = getattr(args[1], "id", None)
    if operation == "find_all":
        fields["offset"] = kwargs.get("offset", 0)
        fields["limit"] = kwargs.get("limit", 50)
    return fields


def _bound_log_fields(instance: Any) -> dict[str, Any]:
    if hasattr(instance, "bound_log_fields"):
        return instance.bound_log_fields()
    if hasattr(instance, "request_context_fields"):
        return instance.request_context_fields()
    return {}


def _build_fields(
    layer: Layer,
    instance: Any,
    operation: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    bound = _bound_log_fields(instance)

    if extra:
        if layer == "http":
            return dict(extra)
        return {**bound, **extra}

    if layer == "repository":
        return {**bound, **_repository_fields(instance, operation, args, kwargs)}

    if layer == "service":
        return {
            **bound,
            "service": instance.__class__.__name__,
            "operation": operation,
        }

    if layer == "controller":
        return {
            **bound,
            "controller": instance.__class__.__name__,
            "handler": operation,
        }

    if layer == "utility":
        name = operation
        if hasattr(instance.__class__, "name"):
            try:
                name = instance.__class__.name()
            except TypeError:
                name = instance.__class__.__name__
        return {
            **bound,
            "utility": name,
            "operation": operation,
        }

    return {**bound, "operation": operation}


def _track_span(
    layer: Layer,
    operation: str,
    duration_ms: float,
    outcome: str,
    fields: dict[str, Any],
    *,
    track: bool,
) -> None:
    if not track:
        return
    span_fields = {key: value for key, value in fields.items() if key != "operation"}
    record_layer_timing(layer, operation, duration_ms, outcome, **span_fields)


def _log_failure(
    logger: Any,
    *,
    config: dict[str, Any],
    fields: dict[str, Any],
    duration_ms: float,
    exc: BaseException,
) -> None:
    fail_fields = {
        **fields,
        "duration_ms": duration_ms,
        "outcome": "error",
    }
    from errors.domain_error import DomainError

    if isinstance(exc, DomainError):
        fail_fields["error_code"] = exc.code
        fail_fields["error_message"] = exc.message
        fail_fields["status_code"] = exc.status_code
        if config["domain_error_level"] == "warn":
            logger.warn(config["failed_message"], code=config["failed_code"], **fail_fields)
            return
        logger.error(config["failed_message"], code=config["failed_code"], **fail_fields)
        return

    fail_fields["error_type"] = type(exc).__name__
    fail_fields["error_message"] = str(exc)
    logger.exception(
        config["failed_message"],
        code=config["failed_code"],
        exc=exc,
        **fail_fields,
    )


async def run_timer(
    instance: Any,
    layer: Layer,
    operation: str,
    coro_fn: Callable[[], Awaitable[Any]],
    *,
    extra: dict[str, Any] | None = None,
    slow_ms: float | None = None,
    logger: Any | None = None,
    track: bool = True,
) -> Any:
    """Run an async callable with layer-specific timing logs."""
    config = _LAYER_CONFIG[layer]
    log = logger or (instance.logger if hasattr(instance, "logger") else instance)
    fields = _build_fields(layer, instance, operation, (), {}, extra)
    log.debug(config["started_message"], code=config["started_code"], **fields)
    started = time.perf_counter()

    try:
        result = await coro_fn()
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        _track_span(layer, operation, duration_ms, "error", fields, track=track)
        _log_failure(log, config=config, fields=fields, duration_ms=duration_ms, exc=exc)
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    _track_span(layer, operation, duration_ms, "ok", fields, track=track)
    complete_fields = {**fields, "duration_ms": duration_ms, "outcome": "ok"}

    if layer == "repository":
        result_count = _result_count(result)
        if result_count is not None:
            complete_fields["result_count"] = result_count
        threshold = slow_ms if slow_ms is not None else getattr(instance, "slow_query_ms", 500.0)
        if duration_ms >= threshold and config.get("slow_code"):
            log.warn(config["slow_message"], code=config["slow_code"], **complete_fields)

    if layer == "http":
        status = int(complete_fields.get("status", 0) or 0)
        threshold = float(complete_fields.get("slow_request_ms", 1000.0))
        if status >= 500 or duration_ms >= threshold:
            log.warn(config["completed_message"], code=config["completed_code"], **complete_fields)
            return result

    log.info(config["completed_message"], code=config["completed_code"], **complete_fields)
    return result


def timer(
    layer: Layer,
    *,
    operation: str | None = None,
    extra: dict[str, Any] | None = None,
    slow_ms: float | None = None,
    track: bool = True,
) -> Callable[[F], F]:
    """Decorator that logs start, duration, and outcome for a bound method."""

    def decorator(fn: F) -> F:
        op = operation or fn.__name__

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                instance = args[0]
                fields = extra or _build_fields(layer, instance, op, args, kwargs, None)

                async def _call() -> Any:
                    return await fn(*args, **kwargs)

                return await run_timer(
                    instance,
                    layer,
                    op,
                    _call,
                    extra=fields,
                    slow_ms=slow_ms,
                    track=track,
                )

            async_wrapper.__timer_layer__ = layer
            async_wrapper.__timer_track__ = track
            async_wrapper.__signature__ = inspect.signature(fn)
            return cast(F, async_wrapper)

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            instance = args[0]
            config = _LAYER_CONFIG[layer]
            logger = instance.logger
            fields = extra or _build_fields(layer, instance, op, args, kwargs, None)
            logger.debug(config["started_message"], code=config["started_code"], **fields)
            started = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                _track_span(layer, op, duration_ms, "error", fields, track=track)
                _log_failure(logger, config=config, fields=fields, duration_ms=duration_ms, exc=exc)
                raise
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            _track_span(layer, op, duration_ms, "ok", fields, track=track)
            logger.info(
                config["completed_message"],
                code=config["completed_code"],
                duration_ms=duration_ms,
                outcome="ok",
                **fields,
            )
            return result

        sync_wrapper.__timer_layer__ = layer
        sync_wrapper.__timer_track__ = track
        sync_wrapper.__signature__ = inspect.signature(fn)
        return cast(F, sync_wrapper)

    return decorator
