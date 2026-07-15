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
        import urllib.parse

        decoded = urllib.parse.unquote(request_path)
        target = (self._root / decoded.lstrip("/")).resolve()
        try:
            target.relative_to(self._root)
            return target
        except ValueError:
            return None

    def _format_propfind_xml(self, path: Path, request_path: str) -> str:
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
        entries = [self._format_propfind_xml(root_path, request_path)]
        if root_path.is_dir():
            for child in sorted(root_path.iterdir()):
                child_path = request_path.rstrip("/") + "/" + child.name
                entries.append(self._format_propfind_xml(child, child_path))
        return '<?xml version="1.0" encoding="utf-8"?>\n<D:multistatus xmlns:D="DAV:">\n' + \
               "\n".join(entries) + "\n</D:multistatus>"

    async def process(self, request_data: dict, call_next: Callable) -> dict:
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
