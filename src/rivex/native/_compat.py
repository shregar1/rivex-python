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
    """Return the first header value matching ``name`` (case-insensitive).

    Prefers the native Rust ``headers_get`` helper when the v2 native
    core is available, and falls back to a linear scan of ``headers``
    otherwise. The lookup is case-insensitive on the name while the
    stored values are returned verbatim.

    Args:
        headers: ``(name, value)`` string pairs in the order they were
            received.
        name: Header name to look up. Comparison is case-insensitive.

    Returns:
        The first matching header value, or ``None`` if no header with
        that name is present.
    """
    if RC_V2:
        result: str | None = _rc.headers_get(headers, name)
        return result
    target = name.lower()
    for k, v in headers:
        if k.lower() == target:
            return v
    return None


def get_request_header(request_data: dict, name: str) -> str | None:
    """Return the first value of header ``name`` from a Rivex request envelope.

    Thin wrapper around :func:`get_header` that materialises the
    request's ``headers`` list before delegating.

    Args:
        request_data: The in-flight request envelope. Only its
            ``headers`` entry is consulted.
        name: Header name to look up (case-insensitive).

    Returns:
        The first matching header value, or ``None`` when the header
        is absent or the envelope has no ``headers`` key.
    """
    return get_header(list(request_data.get("headers", [])), name)


def json_error_response(status: int, detail: str) -> dict:
    """Build a JSON-encoded error response envelope.

    Args:
        status: HTTP status code to put on the response.
        detail: The human-readable error message; will be wrapped in a
            ``{"detail": ...}`` object and serialised as JSON.

    Returns:
        A response dict shaped like ``{status, headers, body}`` with
        ``Content-Type: application/json`` and the serialised body
        already encoded as UTF-8 bytes.
    """
    return {
        "status": status,
        "headers": [("content-type", "application/json")],
        "body": json.dumps({"detail": detail}).encode(),
    }


def parse_cookies(cookie_header: str) -> dict[str, str]:
    """Parse a raw ``Cookie`` header into a ``{name: value}`` dict.

    Delegates to the native parser when the Rust core is available,
    otherwise splits on ``;`` and ``=`` to extract each ``name=value``
    pair. Leading and trailing whitespace around each piece is
    stripped; pairs without an ``=`` are silently dropped.

    Args:
        cookie_header: The raw ``Cookie`` header value, or an empty
            string when no cookie header is present.

    Returns:
        A dict mapping cookie name to cookie value, in the order they
        appeared in the header. Returns an empty dict for an empty
        input.
    """
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
    """Extract and parse the ``Cookie`` header from a Rivex request envelope.

    Convenience wrapper that looks up the ``cookie`` header and feeds
    it through :func:`parse_cookies`. Returns an empty dict when the
    request has no cookie header.

    Args:
        request_data: The in-flight request envelope.

    Returns:
        Parsed cookies as a ``{name: value}`` dict, or ``{}`` when
        the request carried no ``Cookie`` header.
    """
    cookie_header = get_request_header(request_data, "cookie")
    return parse_cookies(cookie_header) if cookie_header else {}


def client_ip(request_data: dict) -> str:
    """Return the best-effort client IP for a Rivex request envelope.

    Prefers the native ``extract_client_ip`` helper when available,
    which understands common proxy/forwarded-header semantics. As a
    fallback, walks ``X-Forwarded-For`` (first entry), then
    ``X-Real-IP``, and finally ``remote_addr`` — defaulting to
    ``127.0.0.1`` when none are present.

    Args:
        request_data: The in-flight request envelope. The
            ``headers`` and ``remote_addr`` keys are consulted.

    Returns:
        The resolved client IP as a string. Never empty.
    """
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
    """Mutate ``response`` to advertise the chosen compression encoding.

    Removes any pre-existing ``content-length`` header (since the body
    has been re-encoded and the original size is no longer valid) and
    appends ``content-encoding`` and ``vary: Accept-Encoding`` so
    downstream caches and intermediaries behave correctly.

    Args:
        response: The response dict whose ``headers`` list will be
            replaced in place.
        encoding: The content-encoding token to advertise, e.g.
            ``"gzip"`` or ``"br"``.
    """
    response["headers"] = [
        (k, v) for k, v in response.get("headers", []) if k.lower() != "content-length"
    ] + [
        ("content-encoding", encoding),
        ("vary", "Accept-Encoding"),
    ]
