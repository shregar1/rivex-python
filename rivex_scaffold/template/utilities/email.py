"""Email delivery with Rivex ``validate_email`` and optional SMTP."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Any

from rivex import validate_email

from abstractions.utility import IUtility
from configs import Settings
from configurations import AppConfiguration
from constants.logger import EMAIL_NOT_CONFIGURED, EMAIL_SENT, EMAIL_SEND_FAILED


class EmailUtility(IUtility):
    """Validate and send transactional email."""

    @classmethod
    def name(cls) -> str:
        return "email"

    def __init__(self, *, settings: Settings | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._settings = settings or AppConfiguration.load().settings
        self._email = self._settings.email

    def is_valid_address(self, address: str) -> bool:
        return validate_email(address)

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        html: str | None = None,
    ) -> bool:
        if not self.is_valid_address(to):
            raise ValueError(f"Invalid email address: {to!r}")

        if not self._email.is_configured:
            self.logger.warn(
                "Email not configured; skipped send",
                code=EMAIL_NOT_CONFIGURED,
                to=to,
                subject=subject,
                body_preview=body[:120],
            )
            return True

        message = EmailMessage()
        message["From"] = self._email.email_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if html is not None:
            message.add_alternative(html, subtype="html")

        try:
            await self._send_smtp(message)
            self.logger.info("Email sent", code=EMAIL_SENT, to=to, subject=subject)
            return True
        except Exception as exc:
            self.logger.error(
                "Email send failed",
                code=EMAIL_SEND_FAILED,
                to=to,
                subject=subject,
                error=str(exc),
            )
            raise

    async def _send_smtp(self, message: EmailMessage) -> None:
        email = self._email
        host = email.smtp_host
        if host is None:
            raise RuntimeError("SMTP host is not configured")

        port = email.smtp_port
        user = email.smtp_user
        password = email.smtp_password

        def _deliver() -> None:
            if email.smtp_use_tls:
                with smtplib.SMTP(host, port, timeout=30) as client:
                    client.starttls()
                    if user and password:
                        client.login(user, password)
                    client.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=30) as client:
                    if user and password:
                        client.login(user, password)
                    client.send_message(message)

        await asyncio.to_thread(_deliver)
