"""``rivex.middleware.access_log`` — Apache-style access log middleware."""

from __future__ import annotations

from collections.abc import Callable

from rivex.native._compat import client_ip
from rivex.middleware.abstraction import IMiddleware


class AccessLogMiddleware(IMiddleware):
    """Logs each request in Apache combined-like format.

    Parameters:
        logger_name: Python logger name (default ``"rivex.access"``).
    """

    def __init__(self, logger_name: str = "rivex.access"):
        import logging

        self.logger = logging.getLogger(logger_name)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Run the middleware chain and log the request/response in Apache combined-like format.

        Times the downstream call, then writes a single INFO line on the
        configured logger of the form ``<ip> "<METHOD> <path>" <status>
        <elapsed_ms>ms``. Used as the lowest-cost access-log layer in
        front of structured JSON logging.

        Args:
            request_data: The in-flight request envelope. The ``method``
                and ``path`` fields are used to render the log line.
            call_next: Awaitable that invokes the next middleware /
                handler and returns the downstream response dict.

        Returns:
            The downstream response dict, unchanged.
        """
        import time

        start = time.monotonic()
        response: dict = await call_next(request_data)
        elapsed = (time.monotonic() - start) * 1000
        method = request_data.get("method", "?")
        path = request_data.get("path", "/")
        status = response.get("status", 0) if isinstance(response, dict) else 0
        ip = client_ip(request_data)
        self.logger.info(f'{ip} "{method} {path}" {status} {elapsed:.1f}ms')
        return response


__all__ = ["AccessLogMiddleware"]
