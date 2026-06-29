from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from rivex._compat import client_ip, get_request_header
from rivex.middleware import Middleware


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON lines."""

    def __init__(self, include_timestamp: bool = True, extra_fields: dict[str, Any] | None = None):
        super().__init__()
        self.include_timestamp = include_timestamp
        self.extra_fields = extra_fields or {}

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "logger": record.name,
        }
        if self.include_timestamp:
            data["timestamp"] = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        # Include any extra attributes set on the record
        for key in record.__dict__:
            if (
                key not in logging.LogRecord("", 0, "", 0, "", (), None).__dict__
                and key != "message"
            ):
                data[key] = record.__dict__[key]
        data.update(self.extra_fields)
        return json.dumps(data, default=str)


class StructuredLogger:
    """Pre-configured structured logger that outputs JSON."""

    def __init__(self, name: str = "rivex", level: int = logging.INFO):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(JSONFormatter())
            self._logger.addHandler(handler)

    def _log(self, level: int, msg: str, **context: Any) -> None:
        extra = {k: v for k, v in context.items()}
        self._logger.log(level, msg, extra=extra)

    def debug(self, msg: str, **ctx: Any) -> None:
        self._log(logging.DEBUG, msg, **ctx)

    def info(self, msg: str, **ctx: Any) -> None:
        self._log(logging.INFO, msg, **ctx)

    def warning(self, msg: str, **ctx: Any) -> None:
        self._log(logging.WARNING, msg, **ctx)

    def error(self, msg: str, **ctx: Any) -> None:
        self._log(logging.ERROR, msg, **ctx)

    def critical(self, msg: str, **ctx: Any) -> None:
        self._log(logging.CRITICAL, msg, **ctx)


class StructuredAccessLogMiddleware(Middleware):
    """Access logging middleware that outputs structured JSON logs."""

    def __init__(self, logger_name: str = "rivex.access", include_headers: bool = False):
        self.logger = StructuredLogger(logger_name)
        self.include_headers = include_headers

    async def process(self, request_data, call_next):
        start = time.monotonic()
        response = await call_next(request_data)
        duration_ms = (time.monotonic() - start) * 1000

        log_data = {
            "method": request_data.get("method", "?"),
            "path": request_data.get("path", "/"),
            "status": response.get("status", 0) if isinstance(response, dict) else 0,
            "duration_ms": round(duration_ms, 2),
            "client_ip": client_ip(request_data),
            "user_agent": get_request_header(request_data, "user-agent") or "",
        }
        if self.include_headers:
            log_data["request_headers"] = dict(request_data.get("headers", []))

        self.logger.info("request", **log_data)
        return response


def configure_logging(
    level: str = "INFO", format: str = "json", logger_name: str = "rivex"
) -> StructuredLogger:
    """Configure framework-wide logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger = StructuredLogger(logger_name, level=log_level)
    return logger
