"""Application configuration singleton."""

from __future__ import annotations

from abstractions.configuration import IConfiguration
from configs import PROJECT_NAME, Settings, get_settings


class AppConfiguration(IConfiguration):
    """Singleton for app-level HTTP/runtime settings."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._app = settings.app
        self.service_name = PROJECT_NAME

    @classmethod
    def source(cls) -> str:
        return "env"

    @classmethod
    def layer_name(cls) -> str:
        return "app"

    @classmethod
    def load(cls) -> "AppConfiguration":
        config = cls(get_settings())
        config.validate()
        return config

    def validate(self) -> None:
        if self._app.port <= 0:
            raise ValueError("PORT must be > 0")

    @property
    def database_url(self) -> str:
        return self.settings.database_url
