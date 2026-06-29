"""Helper module for the Rivex benchmark.

Lives next to ``run_bench.py`` and is imported by both the parent
benchmark driver and the per-engine subprocesses. Keeps the app
construction and the engine-runner registry in one place.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the in-tree rivex importable in subprocesses that started
# with an empty ``sys.path``.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def make_app():
    """Build the Rivex app used by the benchmark workloads."""
    import rivex
    from rivex.caching import cached_response

    app = rivex.Rivex(title="bench", version="0.0.0", landing_page=False)

    @app.get("/hello")
    @cached_response(ttl=300)
    async def hello():
        return {"hello": "world"}

    @app.get("/json")
    async def json_route():
        return {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
            ],
            "total": 2,
        }

    @app.get("/users/{user_id:int}")
    async def get_user(user_id: int):
        return {"id": user_id, "name": f"user-{user_id}"}

    # Const route — served from the pre-baked cache.
    app.add_const_route(
        "GET",
        "/health",
        status=200,
        body=b"OK",
        headers={"content-type": "text/plain"},
    )
    return app


def _run_async(app, port: int) -> None:
    app.run_async(host="127.0.0.1", port=port)


def _run_sync(app, port: int) -> None:
    app.run_sync(host="127.0.0.1", port=port)


def _run_asgi(app, port: int) -> None:
    import uvicorn

    from rivex.asgi import ASGIAdapter

    uvicorn.run(
        ASGIAdapter(app),
        host="127.0.0.1",
        port=port,
        log_level="error",
        access_log=False,
    )


ENGINE_RUNNERS = {
    "async": _run_async,
    "sync": _run_sync,
    "asgi": _run_asgi,
}
