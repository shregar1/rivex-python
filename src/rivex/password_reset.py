from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from typing import Any


class PasswordReset:
    """Password reset token generation, validation, and email flow.

    Usage::

        reset = PasswordReset(secret_key="my-secret")
        token = reset.generate_token(user_id=123)
        user_id = reset.validate_token(token)  # returns user_id or None
    """

    def __init__(
        self,
        secret_key: str,
        token_expiry: int = 3600,
        email_backend: Any = None,
        from_email: str = "noreply@rivex.dev",
    ):
        self._secret_key = secret_key
        self._token_expiry = token_expiry
        self._email_backend = email_backend
        self._from_email = from_email

    def generate_token(self, user_id: Any) -> str:
        exp = int(time.time()) + self._token_expiry
        payload = json.dumps({"user_id": str(user_id), "exp": exp, "jti": str(uuid.uuid4())},
                             separators=(",", ":"))
        encoded = payload.encode()
        sig = hmac.new(self._secret_key.encode(), encoded, hashlib.sha256).hexdigest()
        return f"{encoded.hex()}.{sig}"

    def validate_token(self, token: str) -> Any | None:
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return None
            encoded = bytes.fromhex(parts[0])
            sig = parts[1]
            expected = hmac.new(self._secret_key.encode(), encoded, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                return None
            payload = json.loads(encoded.decode())
            if payload["exp"] < time.time():
                return None
            return payload["user_id"]
        except Exception:
            return None

    async def send_reset_email(
        self,
        user_id: Any,
        email: str,
        reset_url: str | None = None,
        **template_vars: Any,
    ) -> bool:
        token = self.generate_token(user_id)
        url = reset_url or f"/reset-password/{token}"
        body = f"Click the link to reset your password: {url}\n\nThis link expires in {self._token_expiry // 60} minutes."
        html = (
            f"<p>Click the link to reset your password:</p>"
            f"<p><a href='{url}'>{url}</a></p>"
            f"<p>This link expires in {self._token_expiry // 60} minutes.</p>"
        )

        if self._email_backend:
            from rivex.email import EmailMessage
            msg = EmailMessage(
                to=[email],
                subject="Password Reset",
                body=body,
                html=html,
                from_email=self._from_email,
            )
            return await self._email_backend.send(msg)
        return False


class PasswordResetMiddleware:
    """Middleware that handles password reset routes.

    Registers:
    - GET /reset-password -> renders form
    - POST /reset-password -> sends reset email
    - GET /reset-password/{token} -> validates token, shows new password form
    - POST /reset-password/{token} -> resets password

    Usage::

        app.add_middleware(PasswordResetMiddleware, secret_key="my-secret")
    """

    def __init__(self, secret_key: str, **kwargs: Any):
        self._reset = PasswordReset(secret_key, **kwargs)
        self._get_user_by_email: Callable | None = None
        self._set_password: Callable | None = None

    def get_user_by_email(self, func: Callable) -> None:
        self._get_user_by_email = func

    def set_password(self, func: Callable) -> None:
        self._set_password = func

    def register_routes(self, router) -> None:
        async def form_get(request):
            return {"html": '<form method="post"><input type="email" name="email" required><button>Reset Password</button></form>'}

        async def form_post(request):
            email = request.form_data.get("email", "")
            if self._get_user_by_email:
                user = await self._get_user_by_email(email)
                if user:
                    await self._reset.send_reset_email(user["id"], email)
            return {"html": "<p>If that email is registered, a reset link has been sent.</p>"}

        async def reset_get(request, token):
            user_id = self._reset.validate_token(token)
            if user_id is None:
                return {"html": "<p>Invalid or expired token.</p>"}
            return {"html": f'<form method="post"><input type="password" name="password" required><input type="hidden" name="token" value="{token}"><button>Set New Password</button></form>'}

        async def reset_post(request, token):
            user_id = self._reset.validate_token(token)
            if user_id is None:
                return {"html": "<p>Invalid or expired token.</p>"}
            password = request.form_data.get("password", "")
            if self._set_password:
                await self._set_password(user_id, password)
            return {"html": "<p>Password has been reset successfully.</p>"}

        router.add_route("GET", "/reset-password", form_get, name="password_reset_form")
        router.add_route("POST", "/reset-password", form_post, name="password_reset_send")
        router.add_route("GET", "/reset-password/{token}", reset_get, name="password_reset_confirm")
        router.add_route("POST", "/reset-password/{token}", reset_post, name="password_reset_done")
