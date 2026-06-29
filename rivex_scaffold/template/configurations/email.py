"""Email configuration singleton."""

from __future__ import annotations

from abstractions.configuration import IConfiguration
from configs import Settings, get_settings


class EmailConfiguration(IConfiguration):
    """Singleton for SMTP/email settings."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._email = settings.email

    @classmethod
    def source(cls) -> str:
        return "env"

    @classmethod
    def layer_name(cls) -> str:
        return "email"

    @classmethod
    def load(cls) -> "EmailConfiguration":
        config = cls(get_settings())
        config.validate()
        return config

    def validate(self) -> None:
        if self._email.smtp_port <= 0:
            raise ValueError("SMTP_PORT must be > 0")
