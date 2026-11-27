"""Static file serving via Rust const routes.

Walks a directory at startup and registers each file as a pre-baked
``const route``. At request time the Rust core serves file bytes from
its HashMap — identical throughput to ``const=True`` handlers
(~500K+ RPS measured on a D32s_v5 Azure VM).

Security:
    Path traversal is prevented by :func:`rivex_core.resolve_static_path`,
    which canonicalises both the ``directory`` root and the requested
    relative path, then verifies the resolved path is inside the root.
    This is the same pattern used by ``actix-files`` and
    ``tower-http::ServeDir`` (CWE-22 guard).

Limitations:
    - Files are loaded into memory at startup. For directories larger
      than ~500 MB, use a traditional streaming file server instead.
    - No range requests (HTTP 206). Large media files should be served
      via a CDN or dedicated file server.
    - Files are read once at startup; changes on disk are NOT reflected
      until the app restarts.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import TYPE_CHECKING

from rivex.native._compat import HAS_CORE
from rivex.native._compat import rc as _rc

if TYPE_CHECKING:
    from rivex.applications.applications import Rivex


def _build_headers(
    mime: str,
    file_size: int,
    cache_control: str | None,
) -> list[tuple[str, str]]:
    """Build the response header list for a static file."""
    headers: list[tuple[str, str]] = [("content-type", mime)]
    if cache_control:
        headers.append(("cache-control", cache_control))
    return headers


def _should_exclude(rel_path: str, exclude_patterns: list[str]) -> bool:
    """Check if a file path matches any exclude glob pattern."""
    if not exclude_patterns:
        return False
    # Check both the full relative path and just the filename
    filename = os.path.basename(rel_path)
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(filename, pattern):
            return True
    return False


def serve_static(
    app: Rivex,
    route: str = "/static",
    directory: str = ".",
    *,
    index_file: str | None = "index.html",
    cache_control: str | None = None,
    exclude: list[str] | None = None,
    max_file_size: int = 10 * 1024 * 1024,
) -> int:
    """Register a directory of static files as Rust const routes.

    See :meth:`rivex.native.NativeHandlers.serve_static` for the
    documented public API. This function is the implementation.

    Args:
        app: Rivex application instance.
        route: URL prefix (must start with ``/``).
        directory: Filesystem path. Resolved relative to CWD.
        index_file: File to serve for directory URLs (``/``-terminated).
            Default ``"index.html"``. ``None`` disables index serving.
        cache_control: ``Cache-Control`` header value for all files.
        exclude: Glob patterns to skip (e.g. ``["*.tmp", "*.log", ".*"]``).
        max_file_size: Files larger than this are skipped (default 10 MB).

    Returns:
        Number of files successfully registered as const routes.

    Raises:
        FileNotFoundError: If ``directory`` does not exist.
        NotADirectoryError: If ``directory`` is not a directory.
    """
    root = Path(directory).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Static directory not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    if not HAS_CORE:
        raise RuntimeError(
            "rivex_core native extension is required for static file serving. "
            "Install it with: pip install rivex-core"
        )

    exclude_patterns = exclude or []
    route_prefix = route.rstrip("/")
    registered = 0

    # Walk the directory tree
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, root)

            # Normalise to forward slashes (URL convention)
            url_rel = rel_path.replace(os.sep, "/")

            # Apply exclusion patterns
            if _should_exclude(url_rel, exclude_patterns):
                continue

            # Skip files that are too large
            try:
                file_size = os.path.getsize(abs_path)
            except OSError:
                continue
            if file_size > max_file_size:
                continue

            # Resolve the path through the Rust core's path-traversal guard.
            # This verifies the file is inside `root` and returns the canonical
            # filesystem path. If it returns None, the path is invalid.
            resolved = _rc.resolve_static_path(str(root), url_rel)
            if resolved is None:
                continue

            # Read the file via the Rust core (fast mmap on Linux)
            result = _rc.read_static_file(resolved)
            if result is None:
                continue
            body, mime, _size = result

            # Build the URL path for this file
            url_path = f"{route_prefix}/{url_rel}"

            # Build headers
            headers = _build_headers(mime, file_size, cache_control)

            # Register as a Rust const route
            app.add_const_route("GET", url_path, 200, body, headers)
            registered += 1

            # If this is an index file, also register the directory URL
            if index_file and filename == index_file:
                dir_url = f"{route_prefix}/{os.path.dirname(url_rel)}".rstrip("/")
                if not dir_url:
                    dir_url = route_prefix
                # Register both "/static/dir" and "/static/dir/" patterns
                app.add_const_route("GET", dir_url, 200, body, headers)
                app.add_const_route("GET", dir_url + "/", 200, body, headers)

    return registered
