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
        self._on_login = callback

    def _get_provider(self, name: str) -> dict:
        provider = self._providers.get(name)
        if not provider:
            raise ValueError(f"Unknown provider: {name}")
        return provider

    def _generate_state(self) -> str:
        return secrets.token_urlsafe(32)

    def _authorize_url(self, provider_name: str, redirect_uri: str) -> str:
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
        for name in self._providers:
            login_path = f"{self._routes_prefix}/{name}/login"
            callback_path = f"{self._routes_prefix}/{name}/callback"

            async def login_route(request, p=name):
                redirect_uri = str(request.url_for("__social_callback", provider=p))
                auth_url = self._authorize_url(p, redirect_uri)
                return {"status": 302, "headers": {"Location": auth_url}}

            async def callback_route(request, p=name):
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
