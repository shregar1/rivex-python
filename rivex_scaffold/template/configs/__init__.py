"""Configuration values: JSON defaults + .env overrides via pydantic-settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

# Project metadata — sourced from pyproject.toml at runtime so the runtime
# always agrees with the package definition. Falls back to sensible defaults
# if pyproject.toml is missing or unparseable (e.g. when running tests).
PROJECT_NAME = "{{project_name}}"
PROJECT_SLUG = "{{project_slug}}"
PROJECT_VERSION = "{{version}}"
PROJECT_DESCRIPTION = "{{description}}"
PROJECT_AUTHOR_NAME = "{{author_name}}"
PROJECT_AUTHOR_EMAIL = "{{author_email}}"
PROJECT_LICENSE = "{{license}}"
PROJECT_REPOSITORY_URL = "{{repository_url}}"
PROJECT_YEAR = "{{year}}"

CONFIGS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = CONFIGS_ROOT.parent
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE_FILE = PROJECT_ROOT / ".env.example"

CONFIG_DOMAINS: tuple[str, ...] = ("paths", "app", "database", "auth", "logging", "email", "sms")


def config_json_path(domain: str) -> Path:
    return CONFIGS_ROOT / domain / "config.json"


def load_domain_config(domain: str) -> dict[str, Any]:
    path = config_json_path(domain)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_defaults() -> dict[str, Any]:
    """Merge all domain ``config.json`` files into flat Settings kwargs."""
    merged: dict[str, Any] = {}
    for domain in CONFIG_DOMAINS:
        merged.update(load_domain_config(domain))
    return merged


_paths = load_domain_config("paths")
LOGS_DIR = PROJECT_ROOT / _paths.get("logs_dir", "logs")
MIGRATIONS_DIR = PROJECT_ROOT / _paths.get("migrations_dir", "migrations")
SCRIPTS_DIR = PROJECT_ROOT / _paths.get("scripts_dir", "scripts")
MEDIA_DIR = PROJECT_ROOT / _paths.get("media_dir", "uploads")
MEDIA_URL_PREFIX = _paths.get("media_url_prefix", "/media").rstrip("/")


@dataclass(frozen=True, slots=True)
class AppConfig:
    node_env: str
    host: str
    port: int
    cors_origin: str
    rate_limit_max: int
    rate_limit_window_seconds: int
    app_name: str = "{{project_name}}"
    powered_by: str = "Rivex"
    admin_enabled: bool = False
    admin_url: str = "/admin"
    admin_token: str = ""
    project_root: str = "."
    admin_codegen_enabled: bool = False

    @property
    def is_production(self) -> bool:
        return self.node_env.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.node_env.lower() == "development"


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    url: str


@dataclass(frozen=True, slots=True)
class AuthConfig:
    jwt_secret: str
    jwt_refresh_secret: str
    jwt_expires_minutes: int
    jwt_refresh_expires_days: int
    algorithm: str = "HS256"

    @property
    def access_ttl_seconds(self) -> int:
        return self.jwt_expires_minutes * 60

    @property
    def refresh_ttl_seconds(self) -> int:
        return self.jwt_refresh_expires_days * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    level: str
    log_file: str | None
    log_stdout: bool
    log_stdout_format: str
    log_stdout_color: str
    log_caller_info: bool
    log_sample_one_in: int


@dataclass(frozen=True, slots=True)
class EmailConfig:
    email_from: str
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    smtp_use_tls: bool

    @property
    def is_configured(self) -> bool:
        return self.smtp_host is not None


@dataclass(frozen=True, slots=True)
class SmsConfig:
    sms_api_url: str | None
    sms_api_key: str | None
    sms_from: str | None

    @property
    def is_configured(self) -> bool:
        return self.sms_api_url is not None


class Settings(BaseSettings):
    """All configuration for the {{project_name}} backend (``config.json`` + ``.env``)."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    node_env: str = Field(alias="NODE_ENV")
    port: int = Field(alias="PORT")
    host: str = Field(alias="HOST")
    database_url: str = Field(alias="DATABASE_URL")

    # Brand / landing-page name. Set APP_NAME in the environment to override.
    app_name: str = Field(default="{{project_name}}", alias="APP_NAME")
    # Small right-aligned attribution on the landing page. Pass empty string to hide.
    powered_by: str = Field(default="Rivex", alias="POWERED_BY")

    # Optional admin dashboard (HTMX + Alpine.js, server-rendered).
    # Set ADMIN_ENABLED=true and ADMIN_TOKEN=<secret> to expose /admin.
    admin_enabled: bool = Field(default=False, alias="ADMIN_ENABLED")
    admin_url: str = Field(default="/admin", alias="ADMIN_URL")
    admin_token: str = Field(default="", alias="ADMIN_TOKEN")

    # Code-generation feature inside the admin dashboard. The generator
    # writes new resources into PROJECT_ROOT.
    project_root: str = Field(default=".", alias="PROJECT_ROOT")
    admin_codegen_enabled: bool = Field(default=False, alias="ADMIN_CODEGEN_ENABLED")

    jwt_secret: str = Field(min_length=32, alias="JWT_SECRET")
    jwt_refresh_secret: str = Field(min_length=32, alias="JWT_REFRESH_SECRET")
    jwt_expires_minutes: int = Field(alias="JWT_EXPIRES_MINUTES")
    jwt_refresh_expires_days: int = Field(alias="JWT_REFRESH_EXPIRES_DAYS")
    algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")

    cors_origin: str = Field(alias="CORS_ORIGIN")
    rate_limit_max: int = Field(alias="RATE_LIMIT_MAX")
    rate_limit_window_seconds: int = Field(alias="RATE_LIMIT_WINDOW_SECONDS")

    log_level: str = Field(alias="LOG_LEVEL")
    log_file: str | None = Field(alias="LOG_FILE")
    log_stdout: bool = Field(alias="LOG_STDOUT")
    log_stdout_format: str = Field(default="pretty", alias="LOG_STDOUT_FORMAT")
    log_stdout_color: str = Field(default="auto", alias="LOG_STDOUT_COLOR")
    log_caller_info: bool = Field(default=True, alias="LOG_CALLER_INFO")
    log_sample_one_in: int = Field(alias="LOG_SAMPLE_ONE_IN")

    email_from: str = Field(alias="EMAIL_FROM")
    smtp_host: str | None = Field(alias="SMTP_HOST")
    smtp_port: int = Field(alias="SMTP_PORT")
    smtp_user: str | None = Field(alias="SMTP_USER")
    smtp_password: str | None = Field(alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(alias="SMTP_USE_TLS")

    sms_api_url: str | None = Field(alias="SMS_API_URL")
    sms_api_key: str | None = Field(alias="SMS_API_KEY")
    sms_from: str | None = Field(alias="SMS_FROM")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Environment and `.env` override `config.json` defaults."""
        return env_settings, dotenv_settings, init_settings, file_secret_settings

    @property
    def app(self) -> AppConfig:
        return AppConfig(
            node_env=self.node_env,
            host=self.host,
            port=self.port,
            cors_origin=self.cors_origin,
            rate_limit_max=self.rate_limit_max,
            rate_limit_window_seconds=self.rate_limit_window_seconds,
            app_name=self.app_name,
            powered_by=self.powered_by,
            admin_enabled=self.admin_enabled,
            admin_url=self.admin_url,
            admin_token=self.admin_token,
            project_root=self.project_root,
            admin_codegen_enabled=self.admin_codegen_enabled,
        )

    @property
    def database(self) -> DatabaseConfig:
        return DatabaseConfig(url=self.database_url)

    @property
    def auth(self) -> AuthConfig:
        return AuthConfig(
            jwt_secret=self.jwt_secret,
            jwt_refresh_secret=self.jwt_refresh_secret,
            jwt_expires_minutes=self.jwt_expires_minutes,
            jwt_refresh_expires_days=self.jwt_refresh_expires_days,
            algorithm=self.algorithm,
        )

    @property
    def logging(self) -> LoggingConfig:
        return LoggingConfig(
            level=self.log_level,
            log_file=self.log_file,
            log_stdout=self.log_stdout,
            log_stdout_format=self.log_stdout_format,
            log_stdout_color=self.log_stdout_color,
            log_caller_info=self.log_caller_info,
            log_sample_one_in=self.log_sample_one_in,
        )

    @property
    def email(self) -> EmailConfig:
        return EmailConfig(
            email_from=self.email_from,
            smtp_host=self.smtp_host,
            smtp_port=self.smtp_port,
            smtp_user=self.smtp_user,
            smtp_password=self.smtp_password,
            smtp_use_tls=self.smtp_use_tls,
        )

    @property
    def sms(self) -> SmsConfig:
        return SmsConfig(
            sms_api_url=self.sms_api_url,
            sms_api_key=self.sms_api_key,
            sms_from=self.sms_from,
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance for the process lifetime."""
    return Settings(**load_json_defaults())


def _load_pyproject_metadata() -> dict[str, str]:
    """Read the [project] table from pyproject.toml.

    Returns an empty dict if the file is missing or unparseable.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if not pyproject.is_file():
        return {}
    try:
        import tomllib
    except ImportError:  # pragma: no cover — Python < 3.11
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict(data.get("project", {}))


def project_metadata() -> dict[str, str]:
    """Return live project metadata, falling back to module-level constants."""
    data = _load_pyproject_metadata()
    return {
        "name": data.get("name", PROJECT_NAME),
        "version": data.get("version", PROJECT_VERSION),
        "description": data.get("description", PROJECT_DESCRIPTION),
    }


AppSettings = Settings

__all__ = [
    "AppSettings",
    "Settings",
    "get_settings",
    "AppConfig",
    "AuthConfig",
    "DatabaseConfig",
    "EmailConfig",
    "LoggingConfig",
    "SmsConfig",
    "PROJECT_NAME",
    "PROJECT_SLUG",
    "PROJECT_VERSION",
    "PROJECT_DESCRIPTION",
    "PROJECT_AUTHOR_NAME",
    "PROJECT_AUTHOR_EMAIL",
    "PROJECT_LICENSE",
    "PROJECT_REPOSITORY_URL",
    "PROJECT_YEAR",
    "PROJECT_ROOT",
    "ENV_FILE",
    "ENV_EXAMPLE_FILE",
    "LOGS_DIR",
    "MIGRATIONS_DIR",
    "SCRIPTS_DIR",
    "MEDIA_DIR",
    "MEDIA_URL_PREFIX",
    "CONFIGS_ROOT",
    "CONFIG_DOMAINS",
    "config_json_path",
    "load_domain_config",
    "load_json_defaults",
    "project_metadata",
]
