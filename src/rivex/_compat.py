from __future__ import annotations

import json

try:
    import rivex_core as _rc

    HAS_CORE = True
except ImportError:
    _rc = None  # type: ignore[assignment]
    HAS_CORE = False

RC_V2 = HAS_CORE and hasattr(_rc, "headers_get")

rc = _rc


def get_header(headers: list[tuple[str, str]], name: str) -> str | None:
    if RC_V2:
        result: str | None = _rc.headers_get(headers, name)
        return result
    target = name.lower()
    for k, v in headers:
        if k.lower() == target:
            return v
    return None


def get_request_header(request_data: dict, name: str) -> str | None:
    return get_header(list(request_data.get("headers", [])), name)


def json_error_response(status: int, detail: str) -> dict:
    return {
        "status": status,
        "headers": [("content-type", "application/json")],
        "body": json.dumps({"detail": detail}).encode(),
    }


def parse_cookies(cookie_header: str) -> dict[str, str]:
    if HAS_CORE:
        parsed: dict[str, str] = _rc.parse_cookies(cookie_header)
        return parsed
    result: dict[str, str] = {}
    for pair in cookie_header.split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def parse_request_cookies(request_data: dict) -> dict[str, str]:
    cookie_header = get_request_header(request_data, "cookie")
    return parse_cookies(cookie_header) if cookie_header else {}


def client_ip(request_data: dict) -> str:
    if HAS_CORE:
        headers = list(request_data.get("headers", []))
        result: str = _rc.extract_client_ip(headers, request_data.get("remote_addr"))
        return result
    return (
        (get_request_header(request_data, "x-forwarded-for") or "").split(",")[0].strip()
        or get_request_header(request_data, "x-real-ip")
        or request_data.get("remote_addr", "127.0.0.1")
    )


def apply_compressed_headers(response: dict, encoding: str) -> None:
    response["headers"] = [
        (k, v) for k, v in response.get("headers", []) if k.lower() != "content-length"
    ] + [
        ("content-encoding", encoding),
        ("vary", "Accept-Encoding"),
    ]
