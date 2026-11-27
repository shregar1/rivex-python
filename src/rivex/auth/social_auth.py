from __future__ import annotations

import json
import secrets
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SocialAuthConfig:
    google: dict | None = None
    github: dict | None = None
    facebook: dict | None = None
    microsoft: dict | None = None
    custom_providers: dict = field(default_factory=dict)

    def provider(self, name: str, **kwargs: Any) -> None:
        """Register a custom OAuth provider with the given configuration.

        The keyword arguments are stored verbatim and later merged into
        the active provider set by :class:`SocialAuthMiddleware`, so any
        provider-specific field (``client_id``, ``client_secret``,
        ``auth_url``, ``token_url``, ``userinfo_url``, ``scope``, etc.)
        can be supplied here.

        Args:
            name: Provider identifier (e.g. ``"linkedin"``).
            **kwargs: Provider configuration values keyed by name.
        """
        self.custom_providers[name] = kwargs


class SocialAuthMiddleware:
    """Middleware that processes OAuth callbacks and creates user sessions.

    Registers routes at ``/auth/{provider}/login`` and ``/auth/{provider}/callback``.
    """

    def __init__(
        self,
        config: SocialAuthConfig | None = None,
        session_key: str = "social_auth",
        routes_prefix: str = "/auth",
    ):
        self._config = config or SocialAuthConfig()
        self._session_key = session_key
        self._routes_prefix = routes_prefix
        self._providers: dict[str, dict] = {}
        self._on_login: Callable | None = None

        # Load configured providers
        if self._config.google:
            self._providers["google"] = {**self._config.google, "auth_url": "https://accounts.google.com/o/oauth2/v2/auth"}
        if self._config.github:
            self._providers["github"] = {**self._config.github, "auth_url": "https://github.com/login/oauth/authorize"}
        if self._config.facebook:
            self._providers["facebook"] = {**self._config.facebook, "auth_url": "https://www.facebook.com/v12.0/dialog/oauth"}
        if self._config.microsoft:
            self._providers["microsoft"] = {**self._config.microsoft, "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"}
        if self._config.custom_providers:
            self._providers.update(self._config.custom_providers)

    def on_login(self, callback: Callable) -> None:
        """Register a callback invoked after a successful social login.

        The callback receives ``(request, provider_name, user_info)`` and
        may return a response override. Returning ``None``/falsy falls
        through to the default ``{"user": ..., "token": ...}`` payload.

        Args:
            callback: Callable to invoke from the OAuth callback route
                once user info has been fetched.
        """
        self._on_login = callback

    def _get_provider(self, name: str) -> dict:
        """Return the configuration dict for a known provider.

        Args:
            name: Provider identifier previously registered on this
                middleware.

        Returns:
            The provider's configuration dict, including the ``auth_url``
            injected at construction time.

        Raises:
            ValueError: If ``name`` was never registered.
        """
        provider = self._providers.get(name)
        if not provider:
            raise ValueError(f"Unknown provider: {name}")
        return provider

    def _generate_state(self) -> str:
        """Return a fresh 32-byte URL-safe token used as OAuth ``state``."""
        return secrets.token_urlsafe(32)

    def _authorize_url(self, provider_name: str, redirect_uri: str) -> str:
        """Build the provider's ``/authorize`` URL with all required params.

        Generates a fresh ``state`` value per call and embeds
        ``client_id``, ``redirect_uri``, ``response_type=code``,
        ``scope`` (defaulting to ``"openid email profile"``) and ``state``
        as query parameters on the provider's authorize endpoint.

        Args:
            provider_name: The provider whose authorize URL is being built.
            redirect_uri: The callback URL the IdP should redirect back to.

        Returns:
            The fully-qualified authorize URL with the OAuth parameters
            URL-encoded into the query string.
        """
        provider = self._get_provider(provider_name)
        params = {
            "client_id": provider["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": provider.get("scope", "openid email profile"),
            "state": self._generate_state(),
        }
        return f"{provider['auth_url']}?{urllib.parse.urlencode(params)}"

    async def _exchange_code(self, provider_name: str, code: str, redirect_uri: str) -> dict:
        """Exchange an authorization code for an access token at the IdP.

        Resolves the token endpoint from the provider config (or the
        built-in map for the bundled providers), then POSTs the standard
        ``authorization_code`` grant body. The response JSON is returned
        without further parsing; the caller pulls ``access_token`` out of
        it.

        Args:
            provider_name: Identifier of the provider whose token endpoint
                should be called.
            code: The authorization code returned by the IdP on the
                callback URL.
            redirect_uri: The same redirect URI used during authorization;
                must match what the IdP has stored.

        Returns:
            Parsed JSON response from the IdP's token endpoint. Typically
            contains ``access_token`` and optionally ``refresh_token``,
            ``id_token``, ``expires_in``, etc.
        """
        import httpx
        provider = self._get_provider(provider_name)
        token_url = provider.get("token_url", "")
        if not token_url:
            token_endpoints = {
                "google": "https://oauth2.googleapis.com/token",
                "github": "https://github.com/login/oauth/access_token",
                "facebook": "https://graph.facebook.com/v12.0/oauth/access_token",
                "microsoft": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            }
            token_url = token_endpoints.get(provider_name, "")

        data = {
            "client_id": provider["client_id"],
            "client_secret": provider["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data=data)
            return resp.json()

    async def _get_user_info(self, provider_name: str, access_token: str) -> dict:
        """Fetch the authenticated user's profile from the IdP.

        Uses the built-in userinfo endpoint for the bundled providers
        (Google, GitHub, Facebook, Microsoft), or the
        ``userinfo_url`` field from the provider config for custom ones.
        The bearer token is sent as ``Authorization: Bearer ...``.

        Args:
            provider_name: Identifier of the provider whose userinfo
                endpoint should be called.
            access_token: The OAuth access token to authenticate against
                the userinfo endpoint.

        Returns:
            Parsed JSON user profile as returned by the IdP. The exact
            shape depends on the provider.
        """
        import httpx
        userinfo_endpoints = {
            "google": "https://www.googleapis.com/oauth2/v2/userinfo",
            "github": "https://api.github.com/user",
            "facebook": "https://graph.facebook.com/me?fields=id,name,email",
            "microsoft": "https://graph.microsoft.com/v1.0/me",
        }
        url = userinfo_endpoints.get(provider_name)
        if not url:
            provider = self._get_provider(provider_name)
            url = provider.get("userinfo_url", "")

        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {access_token}"}
            resp = await client.get(url, headers=headers)
            return resp.json()

    def register_routes(self, router) -> None:
        """Attach ``/login`` and ``/callback`` routes for every provider.

        For each registered provider, this method installs a ``GET``
        ``/auth/{name}/login`` route that 302-redirects to the IdP's
        authorize URL, and a ``GET`` ``/auth/{name}/callback`` route that
        exchanges the authorization code, fetches the user profile, runs
        the configured ``on_login`` hook, and returns the user info
        together with the access token.

        Args:
            router: The :class:`Rivex` or :class:`Router` to attach the
                routes to. The router must expose ``add_route`` and the
                request must support ``url_for`` to compute the callback
                URL.
        """
        for name in self._providers:
            login_path = f"{self._routes_prefix}/{name}/login"
            callback_path = f"{self._routes_prefix}/{name}/callback"

            async def login_route(request, p=name):
                """Redirect the user to the provider's authorize endpoint.

                Computes the absolute callback URL via the router's
                ``url_for`` and forwards the user-agent to the IdP with
                a freshly generated ``state`` value.

                Args:
                    request: The inbound request used to resolve the
                        callback URL.
                    p: Captured provider name from the enclosing loop.

                Returns:
                    A 302 response dict whose ``Location`` header points
                    at the IdP authorize URL.
                """
                redirect_uri = str(request.url_for("__social_callback", provider=p))
                auth_url = self._authorize_url(p, redirect_uri)
                return {"status": 302, "headers": {"Location": auth_url}}

            async def callback_route(request, p=name):
                """Exchange the auth code and return the user profile.

                Pulls the ``code`` query parameter, exchanges it for an
                access token via :meth:`_exchange_code`, fetches the
                user info via :meth:`_get_user_info`, and optionally
                runs the ``on_login`` callback. Returns a 400 tuple if
                either the code or the access token is missing.

                Args:
                    request: The inbound callback request.
                    p: Captured provider name from the enclosing loop.

                Returns:
                    A 400 ``(payload, status)`` tuple on failure, or
                    the ``on_login`` callback's return value when it
                    produces one. Otherwise a dict containing ``user``
                    and ``token`` keys.
                """
                code = request.query_params.get("code")
                code = request.query_params.get("code")
                if not code:
                    return {"error": "No authorization code provided"}, 400
                redirect_uri = str(request.url_for("__social_callback", provider=p))
                token_data = await self._exchange_code(p, code, redirect_uri)
                access_token = token_data.get("access_token")
                if not access_token:
                    return {"error": "Failed to obtain access token"}, 400
                user_info = await self._get_user_info(p, access_token)
                if self._on_login:
                    result = self._on_login(request, p, user_info)
                    if result:
                        return result
                return {"user": user_info, "token": access_token}

            router.add_route("GET", login_path, login_route, name=f"__social_login_{name}")
            router.add_route("GET", callback_path, callback_route, name=f"__social_callback_{name}")
