from __future__ import annotations

from rivex.core._compat import get_request_header
from rivex.middleware.middleware import Middleware


class BaseVersioning:
    """Base class for API versioning."""

    default_version: str = "1"

    def determine_version(self, request_data: dict) -> str | None:
        raise NotImplementedError


class URLPathVersioning(BaseVersioning):
    """Extract version from URL path prefix: /v1/users -> version="1"."""

    prefix: str = "v"

    def determine_version(self, request_data):
        path = request_data.get("path", "/")
        parts = path.strip("/").split("/")
        if parts and parts[0].startswith(self.prefix):
            return parts[0][len(self.prefix) :]
        return self.default_version


class HeaderVersioning(BaseVersioning):
    """Extract version from custom header: Accept-Version: 2."""

    header_name: str = "accept-version"

    def determine_version(self, request_data):
        value = get_request_header(request_data, self.header_name)
        return value.strip() if value else self.default_version


class QueryParamVersioning(BaseVersioning):
    """Extract version from query parameter: ?version=2."""

    param_name: str = "version"

    def determine_version(self, request_data):
        from urllib.parse import parse_qs

        qs = request_data.get("query_string", "")
        params = parse_qs(qs)
        values = params.get(self.param_name)
        if values:
            return values[0]
        return self.default_version


class AcceptHeaderVersioning(BaseVersioning):
    """Extract version from Accept header media type: Accept: application/json; version=2."""

    def determine_version(self, request_data):
        accept = get_request_header(request_data, "accept")
        if accept:
            for part in accept.split(";"):
                part = part.strip()
                if part.startswith("version="):
                    return part.split("=", 1)[1].strip()
        return self.default_version


class VersionMiddleware(Middleware):
    """Adds API version to request data for handlers to access."""

    def __init__(self, versioning: BaseVersioning | type | None = None, default_version: str = "1"):
        if versioning is None:
            versioning = URLPathVersioning()
        elif isinstance(versioning, type):
            versioning = versioning()
        versioning.default_version = default_version  # type: ignore[union-attr]
        self.versioning = versioning

    async def process(self, request_data, call_next):
        version = self.versioning.determine_version(request_data)
        request_data = dict(request_data)
        request_data["api_version"] = version
        return await call_next(request_data)
