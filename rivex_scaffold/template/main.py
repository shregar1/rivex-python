"""{{project_name}} — Rivex + ORMX entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rivex import CORSMiddleware, HTTPException, Rivex, RequestValidationError, StaticFiles
from ormx import connect, disconnect

import models  # noqa: F401 — register ORMX model registry
from errors import DomainError
from dtos.response import APIEnvelopeResponse
from rivex.native._compat import get_request_header
from configs import (
    MEDIA_DIR,
    MEDIA_URL_PREFIX,
    PROJECT_NAME,
    PROJECT_VERSION,
    project_metadata,
)
from constants.api import PLATFORM_NAME
from constants.logger import APP_STARTED, APP_SHUTDOWN, DOMAIN_ERROR
from configurations import AppConfiguration, LoggingConfiguration, PathsConfiguration
from controllers import ALL_CONTROLLERS
from middlewares import RequestIdMiddleware
from utilities.api_envelope import envelope_from_http_exception
from utilities.logger_adapter import get_logger, shutdown_logging

config = AppConfiguration.load()
logger = get_logger(component="main")
_meta = project_metadata()
SERVICE_NAME = _meta.get("name", PROJECT_NAME)
SERVICE_VERSION = _meta.get("version", PROJECT_VERSION)

# Brand / landing-page name. Override via APP_NAME in the environment; falls
# back to the project name, then to "Rivex" so the framework default is
# preserved when the user has not customised it.
APP_NAME = config.settings.app_name or PLATFORM_NAME or PROJECT_NAME
POWERED_BY = config.settings.powered_by or "Rivex"

# Admin dashboard — mounted when ADMIN_ENABLED=true. Set ADMIN_TOKEN to a
# strong random secret in production; an empty token disables the auth check
# (the dashboard is then publicly readable — only safe in local dev).
ADMIN_ENABLED = config.settings.admin_enabled
ADMIN_URL = config.settings.admin_url
ADMIN_TOKEN = config.settings.admin_token or None

# Project root for the in-dashboard code generator. Defaults to the current
# working directory. The generator writes new resources (model, repo,
# services, controller, DTOs, etc.) into this directory.
PROJECT_ROOT = Path(config.settings.project_root).resolve()
ADMIN_CODEGEN_ENABLED = config.settings.admin_codegen_enabled

app = Rivex(
    title=PLATFORM_NAME,
    version=SERVICE_VERSION,
    description="{{description}}",
    app_name=APP_NAME,
    powered_by=POWERED_BY,
    admin_url=ADMIN_URL if ADMIN_ENABLED else None,
    admin_token=ADMIN_TOKEN,
)
# Expose project_root on the app so the admin codegen partial can find it.
app.project_root = PROJECT_ROOT  # type: ignore[attr-defined]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.settings.app.cors_origin],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(RequestIdMiddleware, service_name=SERVICE_NAME, service_version=SERVICE_VERSION)

for controller in ALL_CONTROLLERS:
    app.include_controller(controller)

MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount(MEDIA_URL_PREFIX, StaticFiles(directory=str(MEDIA_DIR)))


def _reference_urn_from_request(request_data: dict) -> str | None:
    return get_request_header(request_data, "x-request-id")


@app.exception_handler(DomainError)
async def handle_domain_error(request, exc: DomainError) -> tuple[int, dict[str, Any]]:
    logger.warn(
        "Domain error returned to client",
        code=DOMAIN_ERROR,
        error_code=exc.code,
        error_message=exc.message,
        status_code=exc.status_code,
    )
    request_data = request if isinstance(request, dict) else {}
    envelope = APIEnvelopeResponse.from_domain_error(
        exc,
        reference_urn=_reference_urn_from_request(request_data),
    )
    return exc.status_code, envelope.model_dump(by_alias=True, mode="json")


@app.exception_handler(HTTPException)
async def handle_http_exception(request, exc: HTTPException) -> tuple[int, dict[str, Any]]:
    request_data = request if isinstance(request, dict) else {}
    envelope = envelope_from_http_exception(exc, reference_urn=_reference_urn_from_request(request_data))
    return exc.status_code, envelope.model_dump(by_alias=True, mode="json")


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request, exc: RequestValidationError) -> tuple[int, dict[str, Any]]:
    request_data = request if isinstance(request, dict) else {}
    errors: list[dict[str, str]] = []
    detail = exc.detail
    if isinstance(detail, list):
        for item in detail:
            if not isinstance(item, dict):
                continue
            loc = item.get("loc") or ()
            field = ".".join(str(part) for part in loc if part != "body") or "body"
            errors.append(
                {
                    "message": str(item.get("msg", "Validation failed")),
                    "field": field,
                    "code": "VALIDATION_ERROR",
                }
            )
    envelope = APIEnvelopeResponse.failed(
        "Validation failed",
        "VALIDATION_ERROR",
        errors=errors or [{"message": "Validation failed", "code": "VALIDATION_ERROR"}],
        reference_urn=_reference_urn_from_request(request_data),
    )
    return exc.status_code, envelope.model_dump(by_alias=True, mode="json")


@app.exception_handler(Exception)
async def handle_unhandled_exception(request, exc: Exception) -> tuple[int, dict[str, Any]]:
    request_data = request if isinstance(request, dict) else {}
    logger.exception(
        "Unhandled exception in request",
        code=DOMAIN_ERROR,
        error_type=type(exc).__name__,
        error_message=str(exc),
    )
    envelope = APIEnvelopeResponse.failed(
        "Something went wrong. Please try again.",
        "INTERNAL_ERROR",
        errors=[{"message": "Something went wrong. Please try again.", "code": "INTERNAL_ERROR"}],
        reference_urn=_reference_urn_from_request(request_data),
    )
    return 500, envelope.model_dump(by_alias=True, mode="json")


@app.on_event("startup")
async def on_startup() -> None:
    PathsConfiguration.load().ensure_dirs()
    LoggingConfiguration.load().setup()
    await connect(config.database_url)
    logger.info(
        "Application started",
        code=APP_STARTED,
        port=config.settings.app.port,
        env=config.settings.app.node_env,
    )


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await disconnect()
    shutdown_logging()
    logger.info("Application shutting down", code=APP_SHUTDOWN)


if __name__ == "__main__":
    app.run(host=config.settings.app.host, port=config.settings.app.port)
