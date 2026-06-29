from typing import Any


class HTTPException(Exception):
    def __init__(
        self,
        status_code: int,
        detail: Any = None,
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self.detail = detail if detail is not None else _default_phrase(status_code)
        self.headers = headers
        super().__init__(self.detail)


class RequestValidationError(HTTPException):
    def __init__(self, errors: list[dict[str, Any]]):
        self.errors_list = errors
        detail = errors
        super().__init__(status_code=422, detail=detail)

    def errors(self) -> list[dict[str, Any]]:
        return self.errors_list


class WebSocketDisconnect(Exception):
    def __init__(self, code: int = 1000, reason: str = ""):
        self.code = code
        self.reason = reason
        super().__init__(f"WebSocket disconnected: {code} {reason}")


def _default_phrase(code: int) -> str:
    phrases = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
    }
    return phrases.get(code, "Error")
