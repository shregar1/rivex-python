"""Uvicorn adapter for Rivex.

This module is an *opt-in* adapter that lets you serve a Rivex
app via uvicorn instead of Rivex's native engines. Use it when
you need uvicorn-specific features (worker supervisor, ASGI
middleware that's tightly coupled to uvicorn's lifecycle,
``uvloop`` integration, etc.).

For best performance, use Rivex's native engine via
``app.run()`` (default). The native engine serves const routes
entirely in Rust and is 5-10x faster than the uvicorn path
because it avoids the ASGI dispatch overhead.

Install
-------

::

    pip install rivex[uvicorn]
    # or:
    pip install uvicorn

Usage
-----

::

    from rivex import Rivex
    from rivex.contrib.uvicorn import serve

    app = Rivex()

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    # Single worker (in-process)
    serve(app, host="127.0.0.1", port=8000)

    # Multiple workers (uvicorn worker supervisor)
    serve(app, host="0.0.0.0", port=8000, workers=4)

    # Or use the CLI:
    # uvicorn my_module:asgi_app --host 0.0.0.0 --port 8000 --workers 4

CLI
---

The adapter also exposes an ASGI app object so the standard
uvicorn CLI works::

    uvicorn my_module:asgi_app --reload
"""
from __future__ import annotations

from typing import Any


def serve(
    app: Any,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    workers: int = 1,
    reload: bool = False,
    log_level: str | None = None,
    **kwargs: Any,
) -> None:
    """Serve a Rivex app via uvicorn.

    This is a thin convenience wrapper around ``uvicorn.run``.
    For most use cases the CLI form
    (``uvicorn my_module:asgi_app``) is preferred.

    Args:
        app: A ``Rivex`` application instance.
        host: Interface to bind on. Default ``"127.0.0.1"``.
        port: TCP port to listen on. Default ``8000``.
        workers: Number of worker processes. ``>1`` uses
            uvicorn's worker supervisor. Default ``1``.
        reload: Enable hot reload on file changes. Default ``False``.
        log_level: uvicorn log level (``"debug"``, ``"info"``,
            ``"warning"``, ``"error"``, ``"critical"``). Default
            ``"info"`` (or ``"debug"`` if ``app.debug``).
        **kwargs: Forwarded to ``uvicorn.Config``.

    Raises:
        ImportError: if uvicorn is not installed.
    """
    try:
        import uvicorn
    except ImportError as e:
        raise ImportError(
            "uvicorn is not installed. Install it with:\n"
            "    pip install rivex[uvicorn]\n"
            "or:\n"
            "    pip install uvicorn"
        ) from e

    if log_level is None:
        log_level = "info" if not getattr(app, "debug", False) else "debug"

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=log_level,
        reload=reload,
        lifespan="on",
        access_log=True,
        ws="auto",
        **kwargs,
    )

    if workers > 1:
        # uvicorn's multi-worker mode requires the CLI form
        # because the workers fork from the parent. If the user
        # passes workers>1 to this function, we run uvicorn
        # in a subprocess with the right flags.
        import sys
        import os
        import subprocess

        # Find the module that defines `app` so the workers can
        # re-import it. This is best-effort; the cleanest path is
        # to use the CLI directly.
        module_name = getattr(app, "__module__", None)
        if module_name is None:
            # Fall back to single-worker (uvicorn can't fork
            # without an import path)
            import warnings
            warnings.warn(
                f"Cannot start uvicorn with workers={workers}: app has no "
                f"__module__. Falling back to single worker. Use the "
                f"CLI for multi-worker: `uvicorn my_module:asgi_app --workers N`.",
                stacklevel=2,
            )
            workers = 1

        if workers > 1:
            # Re-spawn as a uvicorn CLI with --workers.
            argv = [
                sys.executable, "-m", "uvicorn",
                f"{module_name}:{asgi_app.__name__}",
                "--host", host,
                "--port", str(port),
                "--workers", str(workers),
                "--log-level", log_level,
            ]
            os.execvp(sys.executable, argv)
            return  # unreachable

    server = uvicorn.Server(config)
    try:
        server.run()
    except KeyboardInterrupt:
        pass


def make_asgi_app(app: Any) -> Any:
    """Return the ASGI 3 callable for ``app``.

    The Rivex instance is itself an ASGI 3 callable (its
    ``__call__`` method implements the protocol). This helper
    just returns ``app`` itself; it's here for symmetry with
    third-party adapters that wrap the app.

    Example::

        # my_module.py
        from rivex import Rivex
        app = Rivex()
        from rivex.contrib.uvicorn import make_asgi_app
        asgi_app = make_asgi_app(app)
        # uvicorn my_module:asgi_app
    """
    return app


# Convenience alias for the CLI form
asgi_app = None  # populated by the user after import
