"""Tier 4 — JWT authentication middleware marker for ``add_middleware``.

Python-side marker class that ``add_middleware`` detects and forwards
to the Rust ``set_jwt_auth`` method. The actual JWT validation happens
in the Rust pipeline — this class just holds the config kwargs::

    from rivex.middleware.middleware_auth import JWTAuthMiddleware

    app.add_middleware(JWTAuthMiddleware, secret="my-secret")
    app.add_middleware(
        JWTAuthMiddleware,
        secret="my-secret",
        algorithm="HS256",
        issuer="myapp",
        audience="api",
    )
"""

from typing import Any


class JWTAuthMiddleware:
    """Marker class for Rust-level JWT validation.

    Every request is checked for a valid ``Authorization: Bearer <token>``
    header. Invalid / missing tokens receive a 401 response.

    Kwargs (all passed to the Rust ``JWTAuthConfig``):

    - ``secret`` (str, required): HMAC secret or PEM-encoded RSA/EC key.
    - ``algorithm`` (str, default ``"HS256"``): ``HS256``, ``HS384``,
      ``HS512``, ``RS256``, ``RS384``, ``RS512``, ``ES256``, ``ES384``.
    - ``issuer`` (str, optional): expected ``iss`` claim.
    - ``audience`` (str, optional): expected ``aud`` claim.
    - ``required`` (bool, default ``True``): reject requests without a
      token when ``True``; allow anonymous requests when ``False``.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._config = kwargs
