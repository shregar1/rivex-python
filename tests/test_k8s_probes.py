from __future__ import annotations

from rivex import Rivex


def test_k8s_liveness_default_not_set():
    app = Rivex()
    assert app.liveness_url is None
    assert app.readiness_url is None


def test_k8s_probes_registered():
    app = Rivex(liveness_url="/healthz", readiness_url="/readyz")

    @app.get("/")
    async def root():
        return {"status": 200, "headers": [], "body": b"ok"}

    from rivex.testing import TestClient
    client = TestClient(app)

    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"

    resp = client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


def test_k8s_probes_with_custom_paths():
    app = Rivex(liveness_url="/live", readiness_url="/ready")

    @app.get("/")
    async def root():
        return {"status": 200, "headers": [], "body": b"ok"}

    from rivex.testing import TestClient
    client = TestClient(app)

    assert client.get("/live").status_code == 200
    assert client.get("/ready").status_code == 200


def test_drain_timeout_parameter():
    app = Rivex(shutdown_timeout=60, drain_timeout=30)
    assert app.shutdown_timeout == 60
    assert app.drain_timeout == 30


def test_drain_timeout_defaults_to_shutdown():
    app = Rivex(shutdown_timeout=45)
    assert app.drain_timeout == 45


def test_graceful_shutdown_hooks():
    hooks_run = []

    app = Rivex()

    @app.on_event("shutdown")
    def on_shutdown():
        hooks_run.append("shutdown")

    @app.get("/")
    async def root():
        return {"status": 200, "headers": [], "body": b"ok"}

    from rivex.testing import TestClient
    client = TestClient(app)
    client.get("/")
    client.__exit__(None, None, None)
    assert "shutdown" in hooks_run
