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
        from_email: str = "sengarsinghshreyansh@gmail.com",
    ):
        self._secret_key = secret_key
        self._token_expiry = token_expiry
        self._email_backend = email_backend
        self._from_email = from_email

    def generate_token(self, user_id: Any) -> str:
        """Mint a signed, time-bound password-reset token for ``user_id``.

        The token format is ``<hex-payload>.<hex-hmac>`` where the payload
        is a compact JSON object containing the user id, an absolute
        ``exp`` epoch, and a fresh ``jti`` UUID, and the HMAC is
        SHA-256 over the payload using :attr:`_secret_key`.

        Args:
            user_id: Opaque user identifier. Will be stringified in the
                payload and returned as-is by :meth:`validate_token`.

        Returns:
            A single string token that can be embedded in a reset link
            and later passed to :meth:`validate_token`.
        """
        exp = int(time.time()) + self._token_expiry
        payload = json.dumps({"user_id": str(user_id), "exp": exp, "jti": str(uuid.uuid4())},
                             separators=(",", ":"))
        encoded = payload.encode()
        sig = hmac.new(self._secret_key.encode(), encoded, hashlib.sha256).hexdigest()
        return f"{encoded.hex()}.{sig}"

    def validate_token(self, token: str) -> Any | None:
        """Verify a reset token and return the user id, or ``None`` if invalid.

        Performs a constant-time HMAC check against :attr:`_secret_key`,
        parses the JSON payload, and confirms that ``exp`` has not
        elapsed. Any exception during parsing is swallowed and treated
        as a validation failure.

        Args:
            token: The token string produced by :meth:`generate_token`.

        Returns:
            The original user id encoded in the token, or ``None`` when
            the signature does not match, the token is malformed, or it
            has expired.
        """
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
        """Generate a reset token and dispatch a reset email to ``email``.

        Mints a fresh token via :meth:`generate_token`, builds a plain-text
        and HTML body containing the reset URL (either supplied or
        ``/reset-password/{token}``), and forwards the message through
        the configured email backend when one was provided at
        construction time.

        Args:
            user_id: The user id to encode in the token.
            email: Destination email address; passed to the backend as
                the ``to`` recipient.
            reset_url: Optional full URL to embed in the email. Defaults
                to ``/reset-password/{token}`` when omitted.
            **template_vars: Reserved for future templating; currently
                unused by the inline body strings.

        Returns:
            ``True`` when the configured email backend accepted the
            message, ``False`` when no backend has been configured or
            the backend's ``send`` returned a falsy value.
        """
        token = self.generate_token(user_id)
        url = reset_url or f"/reset-password/{token}"
        body = f"Click the link to reset your password: {url}\n\nThis link expires in {self._token_expiry // 60} minutes."
        html = (
            f"<p>Click the link to reset your password:</p>"
            f"<p><a href='{url}'>{url}</a></p>"
            f"<p>This link expires in {self._token_expiry // 60} minutes.</p>"
        )

        if self._email_backend:
            from rivex.web.email import EmailMessage
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
        """Register the callable used to look up a user by email address.

        The function should accept a single ``email`` string and return
        an awaitable resolving to the user record (or ``None`` when no
        such user exists). It is invoked by the ``POST /reset-password``
        route and must be safe to call for unknown addresses.

        Args:
            func: Async or sync callable that fetches a user by email.
        """
        self._get_user_by_email = func

    def set_password(self, func: Callable) -> None:
        """Register the callable used to persist a new password for a user.

        The function should accept ``(user_id, password)`` and be
        awaitable. It is invoked from the
        ``POST /reset-password/{token}`` route after a successful token
        validation, and is responsible for hashing and persisting the
        new password.

        Args:
            func: Async or sync callable that updates the password.
        """
        self._set_password = func

    def register_routes(self, router) -> None:
        """Attach the four password-reset routes to ``router``.

        Wires up:

        - ``GET /reset-password`` → email entry form.
        - ``POST /reset-password`` → looks up the user and emails a
          reset link (if a user resolver is registered).
        - ``GET /reset-password/{token}`` → renders the new-password
          form when the token validates, else an error message.
        - ``POST /reset-password/{token}`` → calls the registered
          ``set_password`` hook when the token is valid.

        Args:
            router: The :class:`Rivex` or :class:`Router` to install the
                routes on. Must expose ``add_route``.
        """
        async def form_get(request):
            """Render the email-entry form for starting a reset.

            Args:
                request: The inbound request (unused for rendering).

            Returns:
                A dict containing the raw HTML of the email entry form.
            """
            return {"html": '<form method="post"><input type="email" name="email" required><button>Reset Password</button></form>'}

        async def form_post(request):
            """Handle the email submission and dispatch a reset link.

            Looks up the user via the registered ``get_user_by_email``
            hook and, when found, calls :meth:`PasswordReset.send_reset_email`.
            The response message is identical whether or not the email is
            known to avoid leaking which addresses are registered.

            Args:
                request: The inbound form submission.

            Returns:
                A dict containing the confirmation HTML payload.
            """
            email = request.form_data.get("email", "")
            if self._get_user_by_email:
                user = await self._get_user_by_email(email)
                if user:
                    await self._reset.send_reset_email(user["id"], email)
            return {"html": "<p>If that email is registered, a reset link has been sent.</p>"}

        async def reset_get(request, token):
            """Render the new-password form when the token is valid.

            Args:
                request: The inbound request (unused for rendering).
                token: The reset token from the URL path.

            Returns:
                A dict containing the new-password form HTML on success,
                or an "Invalid or expired token" message otherwise.
            """
            user_id = self._reset.validate_token(token)
            if user_id is None:
                return {"html": "<p>Invalid or expired token.</p>"}
            return {"html": f'<form method="post"><input type="password" name="password" required><input type="hidden" name="token" value="{token}"><button>Set New Password</button></form>'}

        async def reset_post(request, token):
            """Apply the new password when the token is valid.

            Validates the token, reads the new password from
            ``request.form_data`` and forwards it to the registered
            ``set_password`` hook (which is responsible for hashing).
            Tokens that fail validation return an error page without
            invoking the hook.

            Args:
                request: The inbound form submission containing the
                    ``password`` field.
                token: The reset token from the URL path.

            Returns:
                A dict containing the success or error HTML payload.
            """
            user_id = self._reset.validate_token(token)
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
