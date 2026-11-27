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
        """Serialize this problem to a plain ``dict`` matching RFC 7807.

        Always includes ``type``, ``title``, and ``status``; adds
        ``detail`` and ``instance`` only when set; finally merges the
        ``extensions`` mapping on top so extension members appear at
        the top level of the document.

        Returns:
            The serialised problem detail as a ``dict``.
        """
        d: dict[str, Any] = {"type": self.type, "title": self.title, "status": self.status}
        if self.detail is not None:
            d["detail"] = self.detail
        if self.instance is not None:
            d["instance"] = self.instance
        d.update(self.extensions)
        return d

    def to_bytes(self) -> bytes:
        """Serialize this problem to UTF-8 encoded JSON bytes.

        Returns:
            The result of ``json.dumps(self.to_dict())`` encoded as
            ``utf-8`` bytes, ready to be used as an HTTP response body.
        """
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
        """Return the HTTP status code carried by the embedded problem.

        Returns:
            The ``status`` field of the underlying :class:`ProblemDetail`.
        """
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
        """Build a ready-to-send Problem Details response envelope.

        Constructs a :class:`ProblemDetail`, JSON-encodes it via
        :meth:`ProblemDetail.to_bytes`, and wraps it in a response
        dict whose ``Content-Type`` is ``application/problem+json`` so
        it can be returned directly from a handler or middleware.

        Args:
            status: HTTP status code to send.
            title: Short, human-readable summary of the problem.
            detail: Optional human-readable explanation specific to
                this occurrence.
            type: URI reference identifying the problem type.
            instance: URI reference identifying the specific occurrence.
            headers: Optional extra response headers to append.
            **extensions: Additional RFC 7807 extension members to
                merge into the problem document.

        Returns:
            A ``{status, headers, body}`` dict suitable as a Rivex
            response envelope.
        """
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
    """Build a 404 :class:`ProblemException` for missing resources.

    Args:
        detail: Human-readable description of what could not be found.
        instance: URI identifying the specific occurrence.
        **kw: Additional RFC 7807 extension members to attach.

    Returns:
        A :class:`ProblemException` with status ``404`` and the
        ``"Not Found"`` title.
    """
    return ProblemException(404, "Not Found", detail=detail, instance=instance, **kw)


def bad_request(
    detail: str | None = None, instance: str | None = None, **kw: Any
) -> ProblemException:
    """Build a 400 :class:`ProblemException` for malformed requests.

    Args:
        detail: Human-readable description of what was malformed.
        instance: URI identifying the specific occurrence.
        **kw: Additional RFC 7807 extension members to attach.

    Returns:
        A :class:`ProblemException` with status ``400`` and the
        ``"Bad Request"`` title.
    """
    return ProblemException(400, "Bad Request", detail=detail, instance=instance, **kw)


def unauthorized(
    detail: str | None = None, instance: str | None = None, **kw: Any
) -> ProblemException:
    """Build a 401 :class:`ProblemException` for unauthenticated callers.

    Args:
        detail: Human-readable description of the authentication failure.
        instance: URI identifying the specific occurrence.
        **kw: Additional RFC 7807 extension members to attach.

    Returns:
        A :class:`ProblemException` with status ``401`` and the
        ``"Unauthorized"`` title.
    """
    return ProblemException(401, "Unauthorized", detail=detail, instance=instance, **kw)


def forbidden(
    detail: str | None = None, instance: str | None = None, **kw: Any
) -> ProblemException:
    """Build a 403 :class:`ProblemException` for permission denials.

    Args:
        detail: Human-readable description of why access is denied.
        instance: URI identifying the specific occurrence.
        **kw: Additional RFC 7807 extension members to attach.

    Returns:
        A :class:`ProblemException` with status ``403`` and the
        ``"Forbidden"`` title.
    """
    return ProblemException(403, "Forbidden", detail=detail, instance=instance, **kw)


def conflict(detail: str | None = None, instance: str | None = None, **kw: Any) -> ProblemException:
    """Build a 409 :class:`ProblemException` for resource conflicts.

    Args:
        detail: Human-readable description of the conflict.
        instance: URI identifying the specific occurrence.
        **kw: Additional RFC 7807 extension members to attach.

    Returns:
        A :class:`ProblemException` with status ``409`` and the
        ``"Conflict"`` title.
    """
    return ProblemException(409, "Conflict", detail=detail, instance=instance, **kw)


def unprocessable(
    detail: str | None = None, instance: str | None = None, **kw: Any
) -> ProblemException:
    """Build a 422 :class:`ProblemException` for semantic validation failures.

    Args:
        detail: Human-readable description of the validation failure.
        instance: URI identifying the specific occurrence.
        **kw: Additional RFC 7807 extension members to attach.

    Returns:
        A :class:`ProblemException` with status ``422`` and the
        ``"Unprocessable Entity"`` title.
    """
    return ProblemException(422, "Unprocessable Entity", detail=detail, instance=instance, **kw)


def internal_error(
    detail: str | None = None, instance: str | None = None, **kw: Any
) -> ProblemException:
    """Build a 500 :class:`ProblemException` for unhandled server errors.

    Args:
        detail: Human-readable description of the failure.
        instance: URI identifying the specific occurrence.
        **kw: Additional RFC 7807 extension members to attach.

    Returns:
        A :class:`ProblemException` with status ``500`` and the
        ``"Internal Server Error"`` title.
    """
    return ProblemException(500, "Internal Server Error", detail=detail, instance=instance, **kw)
