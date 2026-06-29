from __future__ import annotations

import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

logger = logging.getLogger("rivex.email")


@dataclass
class EmailMessage:
    to: list[str]
    cc: list[str] | None = None
    bcc: list[str] | None = None
    subject: str = ""
    body: str = ""
    html: str | None = None
    from_email: str = ""
    attachments: list[dict] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)

    def _build_mime(self) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = self.subject
        msg["From"] = self.from_email
        msg["To"] = ", ".join(self.to)
        if self.cc:
            msg["Cc"] = ", ".join(self.cc)
        for k, v in self.headers.items():
            msg[k] = v

        if self.body:
            msg.attach(MIMEText(self.body, "plain"))
        if self.html:
            msg.attach(MIMEText(self.html, "html"))

        for attachment in self.attachments:
            filename = attachment.get("filename", "attachment")
            content = attachment.get("content", b"")
            mime_type = attachment.get("mime_type", "application/octet-stream")
            part = MIMEApplication(content, _subtype=mime_type.split("/")[-1])
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            msg.attach(part)

        return msg

    def recipients(self) -> list[str]:
        return self.to + (self.cc or []) + (self.bcc or [])


class EmailBackend(ABC):
    @abstractmethod
    async def send(self, message: EmailMessage) -> bool:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class SmtpBackend(EmailBackend):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 25,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = False,
        use_ssl: bool = False,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._use_ssl = use_ssl

    async def send(self, message: EmailMessage) -> bool:
        mime = message._build_mime()
        try:
            if self._use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(self._host, self._port, context=context)
            else:
                server = smtplib.SMTP(self._host, self._port)
                if self._use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)

            if self._username and self._password:
                server.login(self._username, self._password)

            server.sendmail(message.from_email, message.recipients(), mime.as_string())
            server.quit()
            logger.info(f"Email sent to {', '.join(message.to)}: {message.subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    async def close(self) -> None:
        pass


class ConsoleBackend(EmailBackend):
    async def send(self, message: EmailMessage) -> bool:
        print(f"--- EMAIL ---")
        print(f"To: {', '.join(message.to)}")
        print(f"Subject: {message.subject}")
        print(f"Body: {message.body[:500]}")
        print(f"--- END ---")
        return True

    async def close(self) -> None:
        pass


class FileBackend(EmailBackend):
    def __init__(self, output_dir: str = "emails"):
        self._output_dir = Path(output_dir)

    async def send(self, message: EmailMessage) -> bool:
        import json
        from datetime import datetime

        self._output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{message.to[0]}.json"
        data = {
            "to": message.to,
            "cc": message.cc,
            "bcc": message.bcc,
            "subject": message.subject,
            "body": message.body,
            "html": message.html,
            "from_email": message.from_email,
        }
        (self._output_dir / filename).write_text(json.dumps(data, indent=2))
        return True

    async def close(self) -> None:
        pass


def get_email_backend(config: dict | None = None) -> EmailBackend:
    conf = config or {}
    backend_type = conf.get("backend", "console")
    if backend_type == "smtp":
        return SmtpBackend(
            host=conf.get("host", "localhost"),
            port=conf.get("port", 587),
            username=conf.get("username"),
            password=conf.get("password"),
            use_tls=conf.get("use_tls", True),
            use_ssl=conf.get("use_ssl", False),
        )
    elif backend_type == "file":
        return FileBackend(output_dir=conf.get("output_dir", "emails"))
    else:
        return ConsoleBackend()


async def send_email(
    to: list[str],
    subject: str,
    body: str = "",
    html: str | None = None,
    from_email: str | None = None,
    config: dict | None = None,
    **kwargs: Any,
) -> bool:
    backend = get_email_backend(config)
    msg = EmailMessage(
        to=to,
        subject=subject,
        body=body,
        html=html,
        from_email=from_email or config.get("from_email", "noreply@rivex.dev"),
        **kwargs,
    )
    return await backend.send(msg)
