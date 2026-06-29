from __future__ import annotations

import functools
import os
from collections.abc import Callable
from typing import Any


class SentryMiddleware:
    """Captures exceptions and sends them to Sentry.

    Usage::

        app.add_middleware(SentryMiddleware, dsn="https://...@.../...")
    """

    def __init__(
        self,
        dsn: str | None = None,
        service_name: str | None = None,
        environment: str | None = None,
        traces_sample_rate: float = 0.0,
        app: Any = None,
    ):
        self._dsn = dsn or os.environ.get("SENTRY_DSN", "")
        self._service_name = service_name or os.environ.get("SENTRY_SERVICE_NAME", "rivex-app")
        self._environment = environment or os.environ.get("SENTRY_ENVIRONMENT", "production")
        self._traces_sample_rate = traces_sample_rate
        self._client = None

        if self._dsn:
            try:
                import sentry_sdk
                sentry_sdk.init(
                    dsn=self._dsn,
                    environment=self._environment,
                    traces_sample_rate=self._traces_sample_rate,
                    server_name=self._service_name,
                )
                self._client = sentry_sdk
            except ImportError:
                pass

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        if self._client is None:
            return await call_next(request_data)

        try:
            result = await call_next(request_data)
            status = result.get("status", 200)
            if status >= 500:
                body = result.get("body", "")
                self._client.capture_message(
                    f"HTTP {status} on {request_data.get('path', '/')}",
                    level="error",
                )
            return result
        except Exception as e:
            self._client.capture_exception(e)
            raise


def configure_sentry(
    dsn: str,
    service_name: str = "rivex-app",
    environment: str = "production",
    traces_sample_rate: float = 0.1,
    before_send: Callable | None = None,
) -> None:
    """One-call Sentry configuration.

    Usage::

        configure_sentry(dsn="https://...", traces_sample_rate=0.2)
    """
    try:
        import sentry_sdk

        kwargs = {
            "dsn": dsn,
            "environment": environment,
            "traces_sample_rate": traces_sample_rate,
            "server_name": service_name,
        }
        if before_send:
            kwargs["before_send"] = before_send

        sentry_sdk.init(**kwargs)
    except ImportError:
        pass


def capture_exception(func: Callable) -> Callable:
    """Decorator to capture exceptions from background tasks.

    Usage::

        @capture_exception
        async def my_task():
            ...
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(e)
            except ImportError:
                pass
            raise

    return wrapper


def set_user_context(user_id: Any, username: str = "", email: str = "") -> None:
    try:
        import sentry_sdk
        sentry_sdk.set_user({"id": str(user_id), "username": username, "email": email})
    except ImportError:
        pass


def set_extra_context(key: str, value: Any) -> None:
    try:
        import sentry_sdk
        sentry_sdk.set_extra(key, value)
    except ImportError:
        pass
