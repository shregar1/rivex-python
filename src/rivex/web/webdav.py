from __future__ import annotations

import datetime
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


class WebDAVMiddleware:
    """WebDAV protocol support for file management over HTTP.

    Implements WebDAV (RFC 4918) methods: PROPFIND, MKCOL, MOVE,
    COPY, PROPPATCH, LOCK, UNLOCK — allowing clients like Windows
    Explorer, macOS Finder, or Cyberduck to browse and manage files.

    Usage::

        app.add_middleware(WebDAVMiddleware, root_dir="/data/files")
    """

    def __init__(
        self,
        root_dir: str = "./webdav_root",
        readonly: bool = False,
        app: Any = None,
    ):
        self._root = Path(root_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._readonly = readonly
        self._locks: dict[str, dict] = {}

    def _resolve_path(self, request_path: str) -> Path | None:
        """Translate a URL path into an absolute filesystem path inside ``self._root``.

        Percent-decodes the path, joins it onto the WebDAV root, and
        resolves ``..`` and symlinks via :meth:`Path.resolve`. The
        resolved path must still be a descendant of ``self._root``
        after resolution; anything that escapes (symlink target outside
        the root, malformed request, etc.) is rejected by returning
        ``None``.

        Args:
            request_path: The URL path (with leading slash) of the
                incoming request.

        Returns:
            The absolute :class:`Path` to serve, or ``None`` when the
            path would escape the configured root and must be denied.
        """
        import urllib.parse

        decoded = urllib.parse.unquote(request_path)
        target = (self._root / decoded.lstrip("/")).resolve()
        try:
            target.relative_to(self._root)
            return target
        except ValueError:
            return None

    def _format_propfind_xml(self, path: Path, request_path: str) -> str:
        """Render a single ``<D:response>`` block for a WebDAV PROPFIND target.

        Builds the XML envelope used by both ``Depth: 0`` PROPFIND
        replies and the per-child rows inside ``Depth: 1`` replies.
        The response includes the resource's display name, last-modified
        time, size, content type, and resourcetype (collection vs. plain
        resource).

        Args:
            path: Filesystem path whose metadata should be reported.
            request_path: URL path matching ``path`` — used verbatim in
                the ``<D:href>`` element so the client sees the same
                URI it requested.

        Returns:
            A UTF-8 XML string containing a single ``<D:response>``
            entry wrapped in a ``<D:multistatus>`` envelope.
        """
        from xml.sax.saxutils import escape

        is_dir = path.is_dir()
        lastmod = datetime.datetime.fromtimestamp(
            path.stat().st_mtime, tz=datetime.timezone.utc
        ).strftime("%a, %d %b %Y %H:%M:%S GMT")
        size = path.stat().st_size if path.is_file() else 0

        collection = (
            '<D:resourcetype><D:collection/></D:resourcetype>'
            if is_dir else
            '<D:resourcetype/>'
        )

        return f"""<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>{escape(request_path)}</D:href>
    <D:propstat>
      <D:prop>
        <D:displayname>{escape(path.name or '/')}</D:displayname>
        <D:getlastmodified>{lastmod}</D:getlastmodified>
        <D:getcontentlength>{size}</D:getcontentlength>
        <D:getcontenttype>{"httpd/unix-directory" if is_dir else "application/octet-stream"}</D:getcontenttype>
        {collection}
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""

    def _format_propfind_multi(self, root_path: Path, request_path: str) -> str:
        """Render a ``Depth: 1`` PROPFIND reply covering ``root_path`` and its direct children.

        The first entry describes the requested collection itself;
        remaining entries describe each child in sorted order. Each
        child entry's URL is built by appending the child name onto the
        parent's URL, so the client can address each entry directly
        with a follow-up ``Depth: 0`` PROPFIND if it wants richer
        metadata.

        Args:
            root_path: The directory requested by the client.
            request_path: URL path of ``root_path`` — used as the
                parent ``<D:href>`` for the first entry and as the
                prefix for child entries.

        Returns:
            A UTF-8 XML string containing one ``<D:response>`` per
            child (plus the root) inside a ``<D:multistatus>``
            envelope.
        """
        entries = [self._format_propfind_xml(root_path, request_path)]
        if root_path.is_dir():
            for child in sorted(root_path.iterdir()):
                child_path = request_path.rstrip("/") + "/" + child.name
                entries.append(self._format_propfind_xml(child, child_path))
        return '<?xml version="1.0" encoding="utf-8"?>\n<D:multistatus xmlns:D="DAV:">\n' + \
               "\n".join(entries) + "\n</D:multistatus>"

    async def process(self, request_data: dict, call_next: Callable) -> dict:
        """Handle WebDAV protocol methods (``PROPFIND``, ``MKCOL``, …) before they reach the next middleware.

        The middleware short-circuits only WebDAV verbs; anything else
        (regular ``GET``/``POST``/…) is passed through to ``call_next``
        unchanged. When a WebDAV verb arrives, the URL is mapped onto
        ``self._root`` (any escape attempt becomes a 403) and the
        per-verb handler builds an RFC 4918-compliant reply. Mutating
        verbs (``MKCOL``, ``MOVE``, ``COPY``, ``LOCK``, ``PROPPATCH``)
        are rejected when the middleware was constructed in
        ``readonly`` mode.

        Args:
            request_data: The in-flight request envelope. Reads
                ``method`` (uppercase), ``path``, and ``headers``
                (``Depth`` and ``Destination`` for the verbs that
                need them).
            call_next: Awaitable that invokes the next middleware /
                handler and returns its response dict. Used for the
                pass-through case and for any verb not in the WebDAV
                set.

        Returns:
            The WebDAV response dict, or the downstream response dict
            (whichever was appropriate).
        """
        method = request_data.get("method", "GET").upper()
        path = request_data.get("path", "/")

        dav_methods = {"PROPFIND", "MKCOL", "MOVE", "COPY", "PROPPATCH", "LOCK", "UNLOCK"}
        if method not in dav_methods:
            return await call_next(request_data)

        resolved = self._resolve_path(path)
        if resolved is None:
            return {"status": 403, "body": "Access denied"}

        if method == "PROPFIND":
            depth = "1"
            headers = request_data.get("headers", {})
            if isinstance(headers, dict):
                depth = headers.get("depth", headers.get("Depth", "1"))

            if not resolved.exists():
                return {"status": 404, "body": "Not found"}

            if depth == "0":
                body = self._format_propfind_xml(resolved, path)
            else:
                body = self._format_propfind_multi(resolved, path)

            return {
                "status": 207,
                "headers": {
                    "Content-Type": "application/xml; charset=utf-8",
                    "DAV": "1, 2",
                },
                "body": body,
            }

        elif method == "MKCOL":
            if self._readonly:
                return {"status": 403, "body": "Read-only"}
            try:
                resolved.mkdir(parents=True, exist_ok=False)
                return {"status": 201, "body": "Created"}
            except FileExistsError:
                return {"status": 405, "body": "Collection already exists"}
            except PermissionError:
                return {"status": 403, "body": "Permission denied"}

        elif method == "MOVE":
            if self._readonly:
                return {"status": 403, "body": "Read-only"}
            dest = ""
            headers = request_data.get("headers", {})
            if isinstance(headers, dict):
                dest = headers.get("destination", headers.get("Destination", ""))
            if not dest:
                return {"status": 400, "body": "Destination header required"}
            dest_resolved = self._resolve_path(dest)
            if dest_resolved is None:
                return {"status": 403, "body": "Access denied"}
            if not resolved.exists():
                return {"status": 404, "body": "Source not found"}
            try:
                dest_resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.rename(dest_resolved)
                return {"status": 204, "body": ""}
            except Exception as e:
                return {"status": 500, "body": str(e)}

        elif method == "COPY":
            if self._readonly:
                return {"status": 403, "body": "Read-only"}
            import shutil
            dest = ""
            headers = request_data.get("headers", {})
            if isinstance(headers, dict):
                dest = headers.get("destination", headers.get("Destination", ""))
            if not dest:
                return {"status": 400, "body": "Destination header required"}
            dest_resolved = self._resolve_path(dest)
            if dest_resolved is None:
                return {"status": 403, "body": "Access denied"}
            if not resolved.exists():
                return {"status": 404, "body": "Source not found"}
            try:
                if resolved.is_dir():
                    shutil.copytree(resolved, dest_resolved)
                else:
                    dest_resolved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(resolved, dest_resolved)
                return {"status": 204, "body": ""}
            except Exception as e:
                return {"status": 500, "body": str(e)}

        elif method == "LOCK":
            if self._readonly:
                return {"status": 403, "body": "Read-only"}
            import uuid
            token = f"urn:uuid:{uuid.uuid4()}"
            self._locks[path] = {"token": token, "depth": "infinity"}
            body = f"""<?xml version="1.0" encoding="utf-8"?>
<D:prop xmlns:D="DAV:">
  <D:lockdiscovery>
    <D:activelock>
      <D:locktype><D:write/></D:locktype>
      <D:lockscope><D:exclusive/></D:lockscope>
      <D:depth>infinity</D:depth>
      <D:locktoken><D:href>{token}</D:href></D:locktoken>
    </D:activelock>
  </D:lockdiscovery>
</D:prop>"""
            return {"status": 200, "headers": {"Content-Type": "application/xml; charset=utf-8"}, "body": body}

        elif method == "UNLOCK":
            headers = request_data.get("headers", {})
            token = ""
            if isinstance(headers, dict):
                lock_token = headers.get("lock-token", headers.get("Lock-Token", ""))
                token = lock_token.strip("<>")
            self._locks.pop(path, None)
            return {"status": 204, "body": ""}

        elif method == "PROPPATCH":
            return {"status": 207, "body": self._format_propfind_xml(resolved, path)}

        return await call_next(request_data)
