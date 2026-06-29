"""Database configuration singleton."""

from __future__ import annotations

from abstractions.configuration import IConfiguration
from configs import Settings, get_settings


class DatabaseConfiguration(IConfiguration):
    """Singleton for database connection settings."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._db = settings.database

    @classmethod
    def source(cls) -> str:
        return "env"

    @classmethod
    def layer_name(cls) -> str:
        return "database"

    @classmethod
    def load(cls) -> "DatabaseConfiguration":
        config = cls(get_settings())
        config.validate()
        return config

    def validate(self) -> None:
        if not self._db.url.startswith("postgres://"):
            raise ValueError("DATABASE_URL must use postgres://")
