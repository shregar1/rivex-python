from __future__ import annotations

import asyncio
from typing import Any

from rivex._compat import HAS_CORE
from rivex._compat import rc as _rc
from rivex.serialization import serialize


class Response:
    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.media_type = media_type
        self._cookies: list[str] = []

    def set_cookie(
        self,
        key: str,
        value: str = "",
        *,
        max_age: int | None = None,
        expires: int | None = None,
        path: str = "/",
        domain: str | None = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: str | None = "lax",
    ) -> None:
        if HAS_CORE:
            cookie_str = _rc.build_set_cookie(
                key,
                value,
                max_age=max_age,
                expires=expires,
                path=path or None,
                domain=domain,
                secure=secure,
                http_only=httponly,
                same_site=samesite,
            )
        else:
            from http.cookies import SimpleCookie

            cookie: SimpleCookie = SimpleCookie()
            cookie[key] = value
            if max_age is not None:
                cookie[key]["max-age"] = str(max_age)
            if expires is not None:
                cookie[key]["expires"] = str(expires)
            if path:
                cookie[key]["path"] = path
            if domain:
                cookie[key]["domain"] = domain
            if secure:
                cookie[key]["secure"] = True
            if httponly:
                cookie[key]["httponly"] = True
            if samesite:
                cookie[key]["samesite"] = samesite
            cookie_str = cookie[key].OutputString()
        self._cookies.append(cookie_str)

    def delete_cookie(
        self,
        key: str,
        *,
        path: str = "/",
        domain: str | None = None,
    ) -> None:
        self.set_cookie(key, "", max_age=0, path=path, domain=domain, expires=0)

    def _to_raw(self) -> dict:
        header_list = list(self.headers.items())
        if self.media_type:
            has_ct = any(k.lower() == "content-type" for k, _ in header_list)
            if not has_ct:
                header_list.append(("content-type", self.media_type))
        for cookie_str in self._cookies:
            header_list.append(("set-cookie", cookie_str))
        body = self._render_body()
        return {"status": self.status_code, "headers": header_list, "body": body}

    def _render_body(self) -> bytes:
        if self.content is None:
            return b""
        if isinstance(self.content, bytes):
            return self.content
        if isinstance(self.content, str):
            return self.content.encode("utf-8")
        return str(self.content).encode("utf-8")


class JSONResponse(Response):
    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type="application/json",
        )

    def _render_body(self) -> bytes:
        return serialize(self.content)


class HTMLResponse(Response):
    def __init__(
        self,
        content: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type="text/html; charset=utf-8",
        )


class PlainTextResponse(Response):
    def __init__(
        self,
        content: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type="text/plain; charset=utf-8",
        )


class RedirectResponse(Response):
    def __init__(
        self,
        url: str,
        status_code: int = 307,
        headers: dict[str, str] | None = None,
    ):
        h = dict(headers) if headers else {}
        h["location"] = url
        super().__init__(content=b"", status_code=status_code, headers=h)


class StreamingResponse(Response):
    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ):
        self._stream = content
        super().__init__(
            content=None, status_code=status_code, headers=headers, media_type=media_type
        )

    def _to_raw(self) -> dict:
        header_list = list(self.headers.items())
        if self.media_type:
            has_ct = any(k.lower() == "content-type" for k, _ in header_list)
            if not has_ct:
                header_list.append(("content-type", self.media_type))
        for cookie_str in self._cookies:
            header_list.append(("set-cookie", cookie_str))

        if HAS_CORE:
            stream_id = _rc.create_stream()
            return {
                "status": self.status_code,
                "headers": header_list,
                "_stream_id": stream_id,
                "_stream_iter": self._stream,
                "_stream_async": hasattr(self._stream, "__aiter__"),
            }

        body = self._render_body()
        return {"status": self.status_code, "headers": header_list, "body": body}

    def _render_body(self) -> bytes:
        chunks: list[bytes] = []
        if hasattr(self._stream, "__aiter__"):

            async def _collect() -> list[bytes]:
                result: list[bytes] = []
                async for chunk in self._stream:
                    if isinstance(chunk, str):
                        result.append(chunk.encode("utf-8"))
                    else:
                        result.append(chunk)
                return result

            # Three cases to handle:
            #   1. No running loop: ``asyncio.run`` works fine.
            #   2. Running loop on this thread: ``run_until_complete``
            #      would deadlock and ``asyncio.run`` is forbidden
            #      from a running loop. Drive the coroutine on a
            #      worker thread that owns a fresh loop.
            #   3. Running loop on another thread: same as (2) —
            #      run on a worker thread to stay independent.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is None or not loop.is_running():
                if loop is not None:
                    chunks = loop.run_until_complete(_collect())
                else:
                    chunks = asyncio.run(_collect())
            else:
                import threading

                holder: dict[str, Any] = {}

                def _worker() -> None:
                    try:
                        holder["chunks"] = asyncio.run(_collect())
                    except BaseException as e:  # noqa: BLE001
                        holder["error"] = e

                t = threading.Thread(target=_worker, daemon=True)
                t.start()
                t.join()
                if "error" in holder:
                    raise holder["error"]
                chunks = holder.get("chunks", [])
        else:
            for chunk in self._stream:
                if isinstance(chunk, str):
                    chunks.append(chunk.encode("utf-8"))
                else:
                    chunks.append(chunk)
        return b"".join(chunks)


class EventSourceResponse(StreamingResponse):
    """Server-Sent Events response."""

    media_type = "text/event-stream"

    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ):
        sse_headers = {"cache-control": "no-cache", "connection": "keep-alive"}
        if headers:
            sse_headers.update(headers)
        super().__init__(
            content=content,
            status_code=status_code,
            headers=sse_headers,
            media_type=self.media_type,
        )

    @staticmethod
    def format_event(
        data: str, event: str | None = None, id: str | None = None, retry: int | None = None
    ) -> str:
        if HAS_CORE:
            result: str = _rc.format_sse_event(data, event=event, id=id, retry=retry)
            return result
        lines = []
        if id is not None:
            lines.append(f"id: {id}")
        if event is not None:
            lines.append(f"event: {event}")
        if retry is not None:
            lines.append(f"retry: {retry}")
        for line in data.split("\n"):
            lines.append(f"data: {line}")
        lines.append("")
        lines.append("")
        return "\n".join(lines)


class FileResponse(Response):
    def __init__(
        self,
        path: str,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
        filename: str | None = None,
    ):
        import mimetypes
        import os

        self._path = path
        if media_type is None:
            media_type, _ = mimetypes.guess_type(path)
            if media_type is None:
                media_type = "application/octet-stream"

        h = dict(headers) if headers else {}
        if filename:
            h["content-disposition"] = f'attachment; filename="{filename}"'

        stat = os.stat(path)
        self._file_size = stat.st_size
        h["content-length"] = str(stat.st_size)

        super().__init__(content=None, status_code=status_code, headers=h, media_type=media_type)

    def _render_body(self) -> bytes:
        with open(self._path, "rb") as f:
            return f.read()

    def _to_raw(self) -> dict:
        raw = super()._to_raw()
        raw.setdefault("headers", [])
        raw["headers"].append(("accept-ranges", "bytes"))
        return raw


class XMLResponse(Response):
    media_type = "application/xml"

    def __init__(
        self,
        content: str | bytes,
        status_code: int = 200,
        headers: dict | None = None,
    ):
        if isinstance(content, str):
            content = content.encode("utf-8")
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type=self.media_type,
        )
