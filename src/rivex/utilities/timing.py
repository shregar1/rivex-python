"""``rivex.utilities.timing`` — timing and operation execution tracking decorator utility."""

from __future__ import annotations

import functools
import inspect
import logging
import time
from typing import Any, Callable, TypeVar, cast

from rivex.utilities.abstraction import IUtility

F = TypeVar("F", bound=Callable[..., Any])


class TimingUtility(IUtility):
    """Encapsulated timing utility for telemetry, logging, and operation tracking."""

    _LAYER_CONFIG: dict[str, dict[str, Any]] = {}

    @classmethod
    def configure_layer(cls, layer: str, **settings: Any) -> None:
        """Configure runtime settings for a specific telemetry layer."""
        cls._LAYER_CONFIG.setdefault(layer, {}).update(settings)

    @classmethod
    def get_layer_config(cls, layer: str) -> dict[str, Any]:
        """Retrieve runtime settings for a specific telemetry layer."""
        return cls._LAYER_CONFIG.get(layer, {})

    @staticmethod
    def build_fields(
        layer: str,
        instance: Any,
        operation: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        result: Any = None,
    ) -> dict[str, Any]:
        """Build telemetry field dictionary."""
        fields: dict[str, Any] = {
            "layer": layer,
            "operation": operation,
            "class": instance.__class__.__name__ if instance is not None else None,
        }
        if result is not None:
            fields["result_type"] = type(result).__name__
        return fields

    @classmethod
    async def run_timer(
        cls,
        instance: Any,
        layer: str,
        operation: str,
        call_fn: Callable[[], Any],
        *,
        extra: dict[str, Any] | None = None,
        slow_ms: float | None = None,
        track: bool = True,
    ) -> Any:
        """Execute async call with timing, logging, and performance thresholds."""
        if not track:
            return await call_fn()

        logger = logging.getLogger(f"rivex.timing.{layer}")
        start_time = time.monotonic()
        status = "SUCCESS"

        try:
            result = await call_fn()
            return result
        except Exception as exc:
            status = "ERROR"
            extra_fields = extra or {}
            extra_fields["error"] = str(exc)
            raise exc
        finally:
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            config = cls.get_layer_config(layer)
            threshold = slow_ms or config.get("slow_ms", 1000.0)

            log_payload = {
                "layer": layer,
                "operation": operation,
                "duration_ms": elapsed_ms,
                "status": status,
                **(extra or {}),
            }

            if elapsed_ms >= threshold:
                logger.warning(
                    f"SLOW OPERATION [{layer}.{operation}]: {elapsed_ms:.2f}ms >= {threshold}ms | {log_payload}"
                )
            else:
                logger.debug(f"TIMING [{layer}.{operation}]: {elapsed_ms:.2f}ms | {log_payload}")

    @classmethod
    def run_timer_sync(
        cls,
        instance: Any,
        layer: str,
        operation: str,
        call_fn: Callable[[], Any],
        *,
        extra: dict[str, Any] | None = None,
        slow_ms: float | None = None,
        track: bool = True,
    ) -> Any:
        """Execute sync call with timing, logging, and performance thresholds."""
        if not track:
            return call_fn()

        logger = logging.getLogger(f"rivex.timing.{layer}")
        start_time = time.monotonic()
        status = "SUCCESS"

        try:
            result = call_fn()
            return result
        except Exception as exc:
            status = "ERROR"
            extra_fields = extra or {}
            extra_fields["error"] = str(exc)
            raise exc
        finally:
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            config = cls.get_layer_config(layer)
            threshold = slow_ms or config.get("slow_ms", 1000.0)

            log_payload = {
                "layer": layer,
                "operation": operation,
                "duration_ms": elapsed_ms,
                "status": status,
                **(extra or {}),
            }

            if elapsed_ms >= threshold:
                logger.warning(
                    f"SLOW OPERATION [{layer}.{operation}]: {elapsed_ms:.2f}ms >= {threshold}ms | {log_payload}"
                )
            else:
                logger.debug(f"TIMING [{layer}.{operation}]: {elapsed_ms:.2f}ms | {log_payload}")

    @classmethod
    def timer(
        cls,
        layer: str,
        *,
        operation: str | None = None,
        extra: dict[str, Any] | None = None,
        slow_ms: float | None = None,
        track: bool = True,
    ) -> Callable[[F], F]:
        """Decorator that logs start, duration, and outcome for a bound method or function."""

        def decorator(fn: F) -> F:
            op = operation or fn.__name__

            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    instance = args[0] if args else None
                    fields = extra or cls.build_fields(layer, instance, op, args, kwargs, None)

                    async def _call() -> Any:
                        return await fn(*args, **kwargs)

                    return await cls.run_timer(
                        instance,
                        layer,
                        op,
                        _call,
                        extra=fields,
                        slow_ms=slow_ms,
                        track=track,
                    )

                async_wrapper.__timer_layer__ = layer  # type: ignore[attr-defined]
                async_wrapper.__timer_track__ = track  # type: ignore[attr-defined]
                async_wrapper.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
                return cast(F, async_wrapper)

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                instance = args[0] if args else None
                fields = extra or cls.build_fields(layer, instance, op, args, kwargs, None)

                def _call() -> Any:
                    return fn(*args, **kwargs)

                return cls.run_timer_sync(
                    instance,
                    layer,
                    op,
                    _call,
                    extra=fields,
                    slow_ms=slow_ms,
                    track=track,
                )

            sync_wrapper.__timer_layer__ = layer  # type: ignore[attr-defined]
            sync_wrapper.__timer_track__ = track  # type: ignore[attr-defined]
            sync_wrapper.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
            return cast(F, sync_wrapper)

        return decorator


__all__ = ["TimingUtility"]
