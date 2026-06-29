from __future__ import annotations

import os
import re

from rivex._compat import HAS_CORE, json_error_response
from rivex._compat import rc as _rc
from rivex.responses import FileResponse


def _file_etag(path: str, stat_result: os.stat_result | None = None) -> str:
    """Generate a weak ETag from file mtime and size."""
    if stat_result is None:
        stat_result = os.stat(path)
    return f'W/"{stat_result.st_mtime:.0f}-{stat_result.st_size}"'


def _parse_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    """Parse a ``Range: bytes=...`` header value.

    Supports::

        bytes=0-499      → first 500 bytes
        bytes=500-       → bytes 500 through end
        bytes=-500       → last 500 bytes

    Returns ``(start, end)`` (0-indexed, inclusive) or ``None`` if the
    header is invalid or unsatisfiable.
    """
    m = re.match(r"^bytes\s*=\s*(\d*)\s*-\s*(\d*)$", range_header.strip())
    if not m:
        return None
    start_str, end_str = m.group(1), m.group(2)
    if start_str and end_str:
        start = int(start_str)
        end = int(end_str)
    elif start_str:
        start = int(start_str)
        end = file_size - 1
    elif end_str:
        suffix = int(end_str)
        start = max(0, file_size - suffix)
        end = file_size - 1
    else:
        return None
    if start < 0 or end >= file_size or start > end:
        return None
    return start, end


class StaticFiles:
    def __init__(
        self,
        *,
        directory: str,
        html: bool = False,
        check_dir: bool = True,
    ):
        self.directory = os.path.abspath(directory)
        self.html = html
        if check_dir and not os.path.isdir(self.directory):
            raise RuntimeError(f"Directory '{directory}' does not exist")

    async def __call__(self, request_data: dict) -> dict:
        path = request_data.get("path", "/")
        path = path.lstrip("/")

        if not path and self.html:
            path = "index.html"

        if HAS_CORE:
            resolved = _rc.resolve_static_path(self.directory, path)
            if resolved is None:
                return _not_found()
            full_path = resolved
        else:
            full_path = os.path.normpath(os.path.join(self.directory, path))
            if not full_path.startswith(self.directory):
                return _not_found()

        if os.path.isdir(full_path):
            if self.html:
                index = os.path.join(full_path, "index.html")
                if os.path.isfile(index):
                    full_path = index
                else:
                    return _not_found()
            else:
                return _not_found()

        if not os.path.isfile(full_path):
            if self.html and not path.endswith(".html"):
                html_path = full_path + ".html"
                if os.path.isfile(html_path):
                    full_path = html_path
                else:
                    return _not_found()
            else:
                return _not_found()

        stat_result = os.stat(full_path)
        file_size = stat_result.st_size
        etag = _file_etag(full_path, stat_result)

        headers = request_data.get("headers") or []

        def _header_value(name: str) -> str | None:
            for k, v in headers:
                if k.lower() == name:
                    return v
            return None

        # If-Match — fail if ETag doesn't match
        if_match = _header_value("if-match")
        if if_match and if_match != "*" and etag not in if_match.split(", "):
            return {
                "status": 412,
                "headers": [("content-type", "application/json"), ("etag", etag)],
                "body": b'{"detail":"Precondition Failed"}',
            }

        # If-None-Match — return 304 for conditional GETs
        if_none_match = _header_value("if-none-match")
        if if_none_match and (if_none_match == "*" or etag in if_none_match.split(", ")):
            method = (request_data.get("method") or "GET").upper()
            if method in ("GET", "HEAD"):
                return {
                    "status": 304,
                    "headers": [("etag", etag)],
                    "body": b"",
                }

        range_header = _header_value("range")

        if range_header:
            parsed = _parse_range(range_header, file_size)
            if parsed is None:
                return {
                    "status": 416,
                    "headers": [
                        ("content-type", "application/json"),
                        ("content-range", f"bytes */{file_size}"),
                        ("accept-ranges", "bytes"),
                    ],
                    "body": b'{"detail":"Range Not Satisfiable"}',
                }
            start, end = parsed
            content_range = f"bytes {start}-{end}/{file_size}"
            partial_size = end - start + 1

            if HAS_CORE:
                body = _rc.read_static_file(full_path)
                if body is None:
                    return _not_found()
                body_bytes, content_type, _ = body
                body_bytes = body_bytes[start:end + 1]
            else:
                with open(full_path, "rb") as f:
                    f.seek(start)
                    body_bytes = f.read(partial_size)
                content_type = _guess_mime(full_path)

            return {
                "status": 206,
                "headers": [
                    ("content-type", content_type),
                    ("content-range", content_range),
                    ("content-length", str(partial_size)),
                    ("accept-ranges", "bytes"),
                    ("etag", etag),
                ],
                "body": body_bytes,
            }

        if HAS_CORE:
            result = _rc.read_static_file(full_path)
            if result is None:
                return _not_found()
            body, content_type, size = result
            return {
                "status": 200,
                "headers": [
                    ("content-type", content_type),
                    ("content-length", str(size)),
                    ("accept-ranges", "bytes"),
                    ("etag", etag),
                ],
                "body": body,
            }

        resp = FileResponse(full_path)
        raw = resp._to_raw()
        raw.setdefault("headers", [])
        raw["headers"].append(("accept-ranges", "bytes"))
        raw["headers"].append(("etag", etag))
        return raw


def _guess_mime(path: str) -> str:
    import mimetypes
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def _not_found() -> dict:
    return json_error_response(404, "Not Found")
