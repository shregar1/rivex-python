from __future__ import annotations

import asyncio
from typing import Any

from rivex.native._compat import HAS_CORE
from rivex.native._compat import rc as _rc
from rivex.serialization.serialization import serialize


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
        """Queue a ``Set-Cookie`` header for inclusion in the response.

        The cookie is built either by the native core or by the standard
        library's :class:`http.cookies.SimpleCookie`, then appended to
        the internal list so :meth:`_to_raw` can attach it to the
        outgoing response.

        Args:
            key: Cookie name.
            value: Cookie value; empty string clears the cookie.
            max_age: Cookie lifetime in seconds.
            expires: Absolute expiry timestamp in seconds since the epoch.
            path: URL path the cookie applies to. Defaults to ``"/"``.
            domain: Optional cookie domain.
            secure: When ``True`` the cookie is only sent over HTTPS.
            httponly: When ``True`` the cookie is hidden from JavaScript.
            samesite: SameSite policy — ``"lax"``, ``"strict"`` or
                ``"none"``. ``None`` omits the attribute.
        """
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
        """Queue a ``Set-Cookie`` header that clears *key* on the client.

        Implementation-wise this is a :meth:`set_cookie` call with an
        empty value, ``max_age=0`` and ``expires=0`` so the browser
        discards the cookie immediately.

        Args:
            key: Cookie name to remove.
            path: Path scope of the deletion cookie.
            domain: Optional domain scope of the deletion cookie.
        """
        self.set_cookie(key, "", max_age=0, path=path, domain=domain, expires=0)

    def _to_raw(self) -> dict:
        """Render the response into a transport-agnostic dict.

        Merges :attr:`headers` with an auto-generated ``Content-Type``
        (when :attr:`media_type` is set and no header overrides it),
        appends every queued ``Set-Cookie`` header, and produces the
        body via :meth:`_render_body`.

        Returns:
            A dict with ``status``, ``headers`` and ``body`` keys that
            the downstream server can serialize onto the wire.
        """
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
        """Encode :attr:`content` as the response body bytes.

        ``None`` yields an empty body, ``bytes`` are passed through,
        ``str`` is UTF-8 encoded, and anything else is coerced via
        :class:`str` before encoding.
        """
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
        """Serialize :attr:`content` to JSON-encoded bytes."""
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
        """Render the streaming response into a transport-friendly dict.

        When the native core is available the stream is registered with
        it and the returned dict carries ``_stream_id``, ``_stream_iter``
        and ``_stream_async`` so the Rust runtime can drive the iterator
        directly. Otherwise the full body is collected eagerly via
        :meth:`_render_body`.
        """
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
        """Collect the underlying stream into a single bytes payload.

        Async iterables are driven via a helper coroutine; the method
        transparently handles the three loop-context cases (no running
        loop, a loop on this thread, a loop on another thread) by
        falling back to a daemon worker thread when it cannot run the
        coroutine on the current loop. String chunks are UTF-8 encoded.
        """
        chunks: list[bytes] = []
        if hasattr(self._stream, "__aiter__"):

            async def _collect() -> list[bytes]:
                """Drain the async stream into a list of bytes chunks.

                Returns:
                    A list with every chunk of the stream, with string
                    chunks already UTF-8 encoded.
                """
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
                    """Drain the stream on a dedicated thread and stash the result.

                    Any exception raised while iterating is captured in
                    ``holder["error"]`` so the main thread can re-raise
                    it after the join, preserving the original failure
                    site.
                    """
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
        """Render a single Server-Sent Event payload as a wire string.

        Args:
            data: Event payload, sent as one or more ``data:`` lines
                split on newlines.
            event: Optional event name (``event:`` field).
            id: Optional event id (``id:`` field).
            retry: Optional reconnection time in milliseconds.

        Returns:
            The formatted event string, ready to be written to the SSE
            stream. The string ends with a blank line as required by the
            SSE protocol.
        """
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
        """Read the entire file at :attr:`_path` and return its bytes."""
        with open(self._path, "rb") as f:
            return f.read()

    def _to_raw(self) -> dict:
        """Render the file response, adding an ``Accept-Ranges: bytes`` hint.

        Returns:
            The raw response dict produced by :meth:`Response._to_raw`
            with an additional ``accept-ranges`` header so clients know
            the server supports range requests on this resource.
        """
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
