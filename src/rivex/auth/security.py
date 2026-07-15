from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from rivex.core._compat import HAS_CORE
from rivex.core._compat import rc as _rc
from rivex.core.exceptions import HTTPException
from rivex.core.requests import Request


class APIKeyHeader:
    def __init__(self, name: str, *, auto_error: bool = True, scheme_name: str | None = None):
        self.name = name
        self.auto_error = auto_error
        self.scheme_name = scheme_name or "APIKeyHeader"
        self.openapi_scheme = {"type": "apiKey", "in": "header", "name": name}

    def __call__(self, request: Request) -> str | None:
        value = request.header(self.name)
        if value is None and self.auto_error:
            raise HTTPException(401, detail="Not authenticated")
        return value


class APIKeyQuery:
    def __init__(self, name: str, *, auto_error: bool = True, scheme_name: str | None = None):
        self.name = name
        self.auto_error = auto_error
        self.scheme_name = scheme_name or "APIKeyQuery"
        self.openapi_scheme = {"type": "apiKey", "in": "query", "name": name}

    def __call__(self, request: Request) -> str | None:
        value = request.query_params.get(self.name)
        if isinstance(value, list):
            value = value[0] if value else None
        if value is None and self.auto_error:
            raise HTTPException(401, detail="Not authenticated")
        return value


class APIKeyCookie:
    def __init__(self, name: str, *, auto_error: bool = True, scheme_name: str | None = None):
        self.name = name
        self.auto_error = auto_error
        self.scheme_name = scheme_name or "APIKeyCookie"
        self.openapi_scheme = {"type": "apiKey", "in": "cookie", "name": name}

    def __call__(self, request: Request) -> str | None:
        value = request.cookies.get(self.name)
        if value is None and self.auto_error:
            raise HTTPException(401, detail="Not authenticated")
        return value


@dataclass(frozen=True)
class HTTPAuthorizationCredentials:
    scheme: str
    credentials: str


class HTTPBearer:
    def __init__(self, *, auto_error: bool = True, scheme_name: str | None = None):
        self.auto_error = auto_error
        self.scheme_name = scheme_name or "HTTPBearer"
        self.openapi_scheme = {"type": "http", "scheme": "bearer"}

    def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        authorization = request.header("authorization")
        if not authorization:
            if self.auto_error:
                raise HTTPException(
                    401,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None

        scheme, _, credentials = authorization.partition(" ")
        if not scheme or not credentials:
            if self.auto_error:
                raise HTTPException(
                    401,
                    detail="Invalid authorization header",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None

        return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)


@dataclass(frozen=True)
class HTTPBasicCredentials:
    username: str
    password: str


class HTTPBasic:
    def __init__(
        self, *, auto_error: bool = True, scheme_name: str | None = None, realm: str | None = None
    ):
        self.auto_error = auto_error
        self.scheme_name = scheme_name or "HTTPBasic"
        self.realm = realm or ""
        self.openapi_scheme = {"type": "http", "scheme": "basic"}

    def __call__(self, request: Request) -> HTTPBasicCredentials | None:
        authorization = request.header("authorization")
        if not authorization:
            if self.auto_error:
                raise HTTPException(
                    401,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": f'Basic realm="{self.realm}"'},
                )
            return None

        if HAS_CORE:
            result = _rc.parse_basic_auth(authorization)
            if result is None:
                if self.auto_error:
                    raise HTTPException(
                        401,
                        detail="Invalid authentication credentials",
                        headers={"WWW-Authenticate": f'Basic realm="{self.realm}"'},
                    )
                return None
            return HTTPBasicCredentials(username=result[0], password=result[1])

        scheme, _, encoded = authorization.partition(" ")
        if scheme.lower() != "basic" or not encoded:
            if self.auto_error:
                raise HTTPException(
                    401,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": f'Basic realm="{self.realm}"'},
                )
            return None

        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except Exception:
            if self.auto_error:
                raise HTTPException(401, detail="Invalid authentication credentials") from None
            return None

        username, _, password = decoded.partition(":")
        return HTTPBasicCredentials(username=username, password=password)


class OAuth2PasswordBearer:
    def __init__(
        self,
        tokenUrl: str,
        *,
        auto_error: bool = True,
        scheme_name: str | None = None,
        scopes: dict[str, str] | None = None,
    ):
        self.tokenUrl = tokenUrl
        self.auto_error = auto_error
        self.scheme_name = scheme_name or "OAuth2PasswordBearer"
        self.scopes = scopes or {}
        self.openapi_scheme = {
            "type": "oauth2",
            "flows": {"password": {"tokenUrl": tokenUrl, "scopes": self.scopes}},
        }
        self.model = self.openapi_scheme

    def __call__(self, request: Request) -> str | None:
        authorization = request.header("authorization")
        if not authorization:
            if self.auto_error:
                raise HTTPException(
                    401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"}
                )
            return None

        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            if self.auto_error:
                raise HTTPException(
                    401,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None
        return token


class OAuth2AuthorizationCodeBearer:
    def __init__(
        self,
        authorizationUrl: str,
        tokenUrl: str,
        *,
        refreshUrl: str | None = None,
        auto_error: bool = True,
        scheme_name: str | None = None,
        scopes: dict[str, str] | None = None,
    ):
        self.authorizationUrl = authorizationUrl
        self.tokenUrl = tokenUrl
        self.refreshUrl = refreshUrl
        self.auto_error = auto_error
        self.scheme_name = scheme_name or "OAuth2AuthorizationCodeBearer"
        self.scopes = scopes or {}
        flow: dict[str, Any] = {
            "authorizationUrl": authorizationUrl,
            "tokenUrl": tokenUrl,
            "scopes": self.scopes,
        }
        if refreshUrl:
            flow["refreshUrl"] = refreshUrl
        self.openapi_scheme = {"type": "oauth2", "flows": {"authorizationCode": flow}}

    def __call__(self, request: Request) -> str | None:
        authorization = request.header("authorization")
        if not authorization:
            if self.auto_error:
                raise HTTPException(
                    401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"}
                )
            return None

        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            if self.auto_error:
                raise HTTPException(
                    401,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None
        return token


class SecurityScopes:
    def __init__(self, scopes: list[str] | None = None):
        self.scopes = scopes or []
        self.scope_str = " ".join(self.scopes)


class OAuth2PasswordRequestForm:
    def __init__(
        self,
        *,
        grant_type: str = "password",
        username: str = "",
        password: str = "",
        scope: str = "",
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        self.grant_type = grant_type
        self.username = username
        self.password = password
        self.scopes = scope.split() if scope else []
        self.client_id = client_id
        self.client_secret = client_secret

    @classmethod
    def _from_request(cls, request: Request) -> OAuth2PasswordRequestForm:
        from urllib.parse import parse_qs

        body = request.body
        if body:
            params = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
        else:
            params = {}

        def _first(key: str, default: str = "") -> str:
            vals = params.get(key, [])
            return vals[0] if vals else default

        return cls(
            grant_type=_first("grant_type", "password"),
            username=_first("username"),
            password=_first("password"),
            scope=_first("scope"),
            client_id=_first("client_id") or None,
            client_secret=_first("client_secret") or None,
        )
