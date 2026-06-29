"""SMS delivery with Rivex ``validate_phone`` and secure OTP generation."""

from __future__ import annotations

from typing import Any

import httpx
from rivex import validate_phone

from abstractions.utility import IUtility
from configs import Settings
from configurations import AppConfiguration
from constants.logger import SMS_NOT_CONFIGURED, SMS_SENT, SMS_SEND_FAILED
from utilities.crypto import CryptoUtility


class SmsUtility(IUtility):
    """Send SMS messages and one-time codes."""

    OTP_LENGTH = 6

    @classmethod
    def name(cls) -> str:
        return "sms"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        crypto: CryptoUtility | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._settings = settings or AppConfiguration.load().settings
        self._sms = self._settings.sms
        self._crypto = crypto or CryptoUtility(**kwargs)

    def is_valid_phone(self, phone: str) -> bool:
        return validate_phone(phone)

    def generate_otp(self, length: int = OTP_LENGTH) -> str:
        return self._crypto.generate_otp(length)

    async def send(self, to: str, message: str) -> bool:
        if not self.is_valid_phone(to):
            raise ValueError(f"Invalid phone number: {to!r}")

        if not self._sms.is_configured:
            self.logger.warn(
                "SMS not configured; skipped send",
                code=SMS_NOT_CONFIGURED,
                to=to,
                message_preview=message[:120],
            )
            return True

        try:
            await self._send_via_api(to, message)
            self.logger.info("SMS sent", code=SMS_SENT, to=to)
            return True
        except Exception as exc:
            self.logger.error(
                "SMS send failed",
                code=SMS_SEND_FAILED,
                to=to,
                error=str(exc),
            )
            raise

    async def send_otp(self, to: str, purpose: str) -> str:
        otp = self.generate_otp()
        message = f"Your {{project_name}} verification code for {purpose} is: {otp}"
        await self.send(to, message)
        return otp

    async def _send_via_api(self, to: str, message: str) -> None:
        sms = self._sms
        url = sms.sms_api_url
        if url is None:
            raise RuntimeError("SMS API URL is not configured")

        headers: dict[str, str] = {}
        if sms.sms_api_key:
            headers["Authorization"] = f"Bearer {sms.sms_api_key}"

        payload = {
            "to": to,
            "message": message,
            "from": sms.sms_from,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
