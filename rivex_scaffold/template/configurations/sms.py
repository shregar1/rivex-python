"""SMS configuration singleton."""

from __future__ import annotations

from abstractions.configuration import IConfiguration
from configs import Settings, get_settings


class SmsConfiguration(IConfiguration):
    """Singleton for SMS provider settings."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._sms = settings.sms

    @classmethod
    def source(cls) -> str:
        return "env"

    @classmethod
    def layer_name(cls) -> str:
        return "sms"

    @classmethod
    def load(cls) -> "SmsConfiguration":
        config = cls(get_settings())
        config.validate()
        return config

    def validate(self) -> None:
        if self._sms.sms_api_url is not None and not self._sms.sms_api_url:
            raise ValueError("SMS_API_URL cannot be empty when provided")
