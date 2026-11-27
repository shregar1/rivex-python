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
        """Run the downstream chain and forward errors to Sentry.

        When the Sentry SDK is not configured, this middleware is a
        pass-through. Otherwise, the downstream chain is awaited and:
        any 5xx response is reported to Sentry as a message at
        ``error`` level, and any raised exception is captured via
        :func:`sentry_sdk.capture_exception` before being re-raised.
        Successful responses (status < 500) are returned unchanged.

        Args:
            request_data: The in-flight request envelope. ``path`` is
                read for the message body of 5xx reports.
            call_next: Awaitable returning the downstream response
                dict.

        Returns:
            The downstream response dict, unmodified.

        Raises:
            Exception: Whatever the downstream chain raised, after
                capturing it with Sentry.
        """
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
        """Run ``func`` and forward any exception to Sentry.

        Awaits the wrapped coroutine, and on exception calls
        :func:`sentry_sdk.capture_exception` (when the Sentry SDK is
        importable) before re-raising so callers still see the
        failure.

        Args:
            *args: Positional arguments forwarded to ``func``.
            **kwargs: Keyword arguments forwarded to ``func``.

        Returns:
            Whatever the wrapped function returns on success.

        Raises:
            Exception: The original exception, re-raised after
                capturing.
        """
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
    """Attach the current user to subsequent Sentry events.

    Thin wrapper over :func:`sentry_sdk.set_user`; the Sentry SDK is
    imported lazily so the function is safe to call when Sentry is
    not installed (it becomes a no-op in that case).

    Args:
        user_id: Stable identifier for the user. Coerced to ``str``.
        username: Optional human-readable username.
        email: Optional email address.
    """
    try:
        import sentry_sdk
        sentry_sdk.set_user({"id": str(user_id), "username": username, "email": email})
    except ImportError:
        pass


def set_extra_context(key: str, value: Any) -> None:
    """Attach a single ``key=value`` to subsequent Sentry events.

    Thin wrapper over :func:`sentry_sdk.set_extra`; the Sentry SDK is
    imported lazily so the function is safe to call when Sentry is
    not installed (it becomes a no-op in that case).

    Args:
        key: Extra context key (will appear as a top-level field on
            the event).
        value: Any JSON-serializable value to attach.
    """
    try:
        import sentry_sdk
        sentry_sdk.set_extra(key, value)
    except ImportError:
        pass
