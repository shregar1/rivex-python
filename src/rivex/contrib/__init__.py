"""Third-party server adapters for Rivex.

Rivex ships with two first-party server engines:
  - ``app.run()``          — Rivex native async (hyper+Tokio). Default.
  - ``app.run_sync()``     — Rivex native sync (std::thread+httparse).

This package contains *opt-in* adapters to third-party servers
that you install separately. They're not part of  core
because they add a Python dependency the user has to opt into.

Available adapters
------------------

* ``rivex.contrib.uvicorn`` — uvicorn (ASGI 3). For users that
  want to deploy on top of uvicorn's worker supervisor or use
  ASGI middleware that only works with uvicorn.

*More adapters will be added over time (hypercorn, granian,
daphne, …). The pattern is always the same: install the
third-party server, then ``from rivex.contrib.<name> import
serve`` and pass your Rivex app.*

Usage
-----

::

    from rivex import Rivex
    app = Rivex()

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    # ── Default: Rivex native (no extra deps) ──
    app.run()

    # ── Uvicorn: opt-in, install `uvicorn` separately ──
    from rivex.contrib.uvicorn import serve
    serve(app, host="127.0.0.1", port=8000, workers=4)
"""
from __future__ import annotations

__all__ = []
