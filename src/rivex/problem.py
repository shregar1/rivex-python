from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProblemDetail:
    """RFC 7807/9457 Problem Details for HTTP APIs.

    Usage:
        raise ProblemException(
            status=404,
            title="User Not Found",
            detail="No user with ID 42 exists.",
            type="https://api.example.com/errors/user-not-found",
            instance="/users/42",
        )
    """

    type: str = "about:blank"
    title: str = ""
    status: int = 500
    detail: str | None = None
    instance: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type, "title": self.title, "status": self.status}
        if self.detail is not None:
            d["detail"] = self.detail
        if self.instance is not None:
            d["instance"] = self.instance
        d.update(self.extensions)
        return d

    def to_bytes(self) -> bytes:
        return json.dumps(self.to_dict()).encode()


class ProblemException(Exception):
    """Exception that renders as RFC 7807 Problem Details JSON."""

    def __init__(
        self,
        status: int = 500,
        title: str = "Internal Server Error",
        detail: str | None = None,
        type: str = "about:blank",
        instance: str | None = None,
        headers: dict[str, str] | None = None,
        **extensions: Any,
    ):
        self.problem = ProblemDetail(
            type=type,
            title=title,
            status=status,
            detail=detail,
            instance=instance,
            extensions=extensions,
        )
        self.headers = headers or {}
        super().__init__(detail or title)

    @property
    def status_code(self) -> int:
        return self.problem.status


class ProblemResponse:
    """Create a Problem Details response dict (for middleware/handlers)."""

    media_type = "application/problem+json"

    @staticmethod
    def create(
        status: int = 500,
        title: str = "Internal Server Error",
        detail: str | None = None,
        type: str = "about:blank",
        instance: str | None = None,
        headers: dict[str, str] | None = None,
        **extensions: Any,
    ) -> dict:
        problem = ProblemDetail(
            type=type,
            title=title,
            status=status,
            detail=detail,
            instance=instance,
            extensions=extensions,
        )
        resp_headers = [("content-type", "application/problem+json")]
        if headers:
            resp_headers.extend(headers.items())
        return {
            "status": status,
            "headers": resp_headers,
            "body": problem.to_bytes(),
        }


def problem_exception_handler(request_data: Any, exc: ProblemException) -> dict:
    """Exception handler that converts ProblemException to Problem Details response.

    Register with: app.exception_handler(ProblemException)(problem_exception_handler)
    """
    resp_headers: list[tuple[str, str]] = [("content-type", "application/problem+json")]
    for k, v in exc.headers.items():
        resp_headers.append((k, v))
    return {
        "status": exc.status_code,
        "headers": resp_headers,
        "body": exc.problem.to_bytes(),
    }


# Common problem detail factories
def not_found(
    detail: str | None = None, instance: str | None = None, **kw: Any
) -> ProblemException:
    return ProblemException(404, "Not Found", detail=detail, instance=instance, **kw)


def bad_request(
    detail: str | None = None, instance: str | None = None, **kw: Any
) -> ProblemException:
    return ProblemException(400, "Bad Request", detail=detail, instance=instance, **kw)


def unauthorized(
    detail: str | None = None, instance: str | None = None, **kw: Any
) -> ProblemException:
    return ProblemException(401, "Unauthorized", detail=detail, instance=instance, **kw)


def forbidden(
    detail: str | None = None, instance: str | None = None, **kw: Any
) -> ProblemException:
    return ProblemException(403, "Forbidden", detail=detail, instance=instance, **kw)


def conflict(detail: str | None = None, instance: str | None = None, **kw: Any) -> ProblemException:
    return ProblemException(409, "Conflict", detail=detail, instance=instance, **kw)


def unprocessable(
    detail: str | None = None, instance: str | None = None, **kw: Any
) -> ProblemException:
    return ProblemException(422, "Unprocessable Entity", detail=detail, instance=instance, **kw)


def internal_error(
    detail: str | None = None, instance: str | None = None, **kw: Any
) -> ProblemException:
    return ProblemException(500, "Internal Server Error", detail=detail, instance=instance, **kw)
