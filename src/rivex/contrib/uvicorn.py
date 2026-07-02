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
    app_var: str | None = None,
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
        app_var: The ``"module:attr"`` import path to the app
            instance, required when ``workers > 1``. Example:
            ``app_var="my_module:app"``. Without it, multi-worker
            mode raises because we cannot infer the user's
            module from the ``Rivex`` instance (its
            ``__module__`` is always ``"rivex.applications"``,
            not the user's module).
        **kwargs: Forwarded to ``uvicorn.Config``.

    Raises:
        ImportError: if uvicorn is not installed.
        ValueError: if ``workers > 1`` and ``app_var`` is missing.
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

    if workers > 1:
        # uvicorn's multi-worker mode requires a stable
        # ``module:attr`` import string so the worker processes can
        # re-import the app. The app's ``__module__`` is always
        # ``rivex.applications`` (the class's defining module), not
        # the user's module, so we cannot infer it. Require the
        # caller to pass ``app_var`` explicitly.
        if not app_var:
            raise ValueError(
                "Multi-worker uvicorn mode (workers>1) requires the "
                "`app_var` argument so the worker processes can "
                "re-import the app. Pass `app_var='your_module:app'` "
                "(the same string you'd give to the uvicorn CLI), or "
                "use the CLI form directly:\n"
                "    uvicorn your_module:app --workers 4"
            )

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
        # Re-spawn as a uvicorn CLI with --workers so uvicorn
        # can fork its worker supervisor. We use ``os.execvp`` so
        # the current process is replaced — anything after this
        # call is unreachable. Note: shutdown hooks / cleanup
        # in this parent process do NOT run; the user is expected
        # to put cleanup in lifespan hooks (which DO run in
        # each worker).
        import os
        import sys

        argv = [
            sys.executable, "-m", "uvicorn",
            app_var,
            "--host", host,
            "--port", str(port),
            "--workers", str(workers),
            "--log-level", log_level,
        ]
        os.execvp(sys.executable, argv)
        return  # unreachable: os.execvp replaces the process

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


def _resolve_asgi_app() -> Any:
    """Resolve the module-level ``asgi_app`` reference.

    Falls back to the most recently-created ``Rivex`` instance if
    no explicit ``asgi_app`` was bound at module scope. Raises a
    clear error if neither is available, rather than returning
    ``None`` (which would let the CLI silently spin up a wrong
    server).
    """
    global asgi_app
    if asgi_app is not None:
        return asgi_app
    # Look at the module that imported us, in case the user
    # bound the app under a different name in their entry module.
    import sys

    for module in list(sys.modules.values()):
        candidate = getattr(module, "asgi_app", None)
        if candidate is not None and not getattr(candidate, "__name__", "").startswith("rivex"):
            asgi_app = candidate
            return candidate
    raise RuntimeError(
        "No `asgi_app` found. Either bind it explicitly in your module:\n"
        "    asgi_app = make_asgi_app(app)\n"
        "or pass the app instance directly to serve()."
    )


# Convenience alias for the CLI form. Initially None; the user
# is expected to assign it (see make_asgi_app above) or the
# ``rivex`` CLI does it automatically.
asgi_app = None
