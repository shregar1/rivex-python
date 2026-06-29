"""Reusable pytest fixtures for Rivex applications.

Usage::

    # tests/conftest.py
    pytest_plugins = ["rivex.testing_fixtures"]


    # tests/test_app.py
    def test_health(client):
        resp = client.get("/health")
        assert resp.status_code == 200


    def test_with_db(client, db):
        db.configure("default", url="sqlite:///:memory:")
        resp = client.get("/users")
        assert resp.status_code == 200
"""

from __future__ import annotations

from typing import Any

import pytest

from rivex import Rivex, TestClient


# ── app fixture ──────────────────────────────────────────────────────────────

class _AppConfig:
    """Holder for per-test app configuration set via ``@pytest.mark.rivex_app``."""

    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}


@pytest.fixture
def app(request: Any) -> Rivex:
    """Yield a fresh ``Rivex()`` instance per test.

    Accepts optional constructor overrides via the
    ``@pytest.mark.rivex_app(key=value)`` marker::

        @pytest.mark.rivex_app(template_dir="tests/templates")
        def test_with_options(client):
            ...
    """
    marker = request.node.get_closest_marker("rivex_app")
    kwargs = marker.kwargs if marker else {}
    return Rivex(**kwargs)


@pytest.fixture
def client(app: Rivex) -> TestClient:
    """Yield a ``TestClient`` wrapping the ``app`` fixture.

    The client enters/exits its lifespan context so startup and
    shutdown hooks run automatically around each test.
    """
    with TestClient(app) as c:
        yield c


# ── database fixture ─────────────────────────────────────────────────────────

@pytest.fixture
def db(app: Rivex) -> Any:
    """Yield an in-memory SQLite database pre-configured on ``app.db``.

    The pool is disconnected at teardown.
    """
    app.db.configure("default", url="sqlite:///:memory:")
    app.db.configure("_test_cache", url="sqlite:///:memory:")
    yield app.db
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(app.db.disconnect_all())
        else:
            loop.run_until_complete(app.db.disconnect_all())
    except RuntimeError:
        pass


# ── HTTP mock fixture ────────────────────────────────────────────────────────

@pytest.fixture
def http_mock() -> Any:
    """Yield a ``respx.MockRouter`` for mocking external HTTP calls.

    Requires ``respx`` installed (included in ``rivex[dev]``).

    Example::

        def test_proxy(client, http_mock):
            http_mock.get("https://api.example.com/data").respond(
                status_code=200, json={"key": "value"}
            )
            resp = client.get("/proxy")
            assert resp.json() == {"key": "value"}
    """
    try:
        import respx
    except ImportError:
        raise ImportError(
            "The ``http_mock`` fixture requires ``respx``. "
            "Install it with: pip install respx"
        ) from None

    with respx.mock:
        yield respx.mock


# ── Redis mock fixture ───────────────────────────────────────────────────────

@pytest.fixture
def redis_mock() -> Any:
    """Yield a ``fakeredis.FakeRedis`` instance for testing Redis-dependent code.

    Requires ``fakeredis`` installed (included in ``rivex[dev]``).

    Example::

        def test_cache(client, redis_mock):
            redis_mock.set("key", "value")
            resp = client.get("/cache/key")
            assert resp.text == "value"
    """
    try:
        import fakeredis
    except ImportError:
        raise ImportError(
            "The ``redis_mock`` fixture requires ``fakeredis``. "
            "Install it with: pip install fakeredis"
        ) from None

    fake = fakeredis.FakeRedis()
    yield fake
    fake.flushall()


# ── S3 mock fixture ─────────────────────────────────────────────────────────

@pytest.fixture
def s3_mock() -> Any:
    """Yield a ``moto``-based S3 mock for testing S3-dependent code.

    Requires ``moto`` and ``aioboto3`` installed.

    Example::

        def test_upload(client, s3_mock):
            s3_mock.create_bucket(Bucket="test")
            resp = client.post("/upload", ...)
            assert resp.status_code == 200
    """
    try:
        import aioboto3
        from moto import mock_aws
    except ImportError:
        raise ImportError(
            "The ``s3_mock`` fixture requires ``moto`` and ``aioboto3``. "
            "Install them with: pip install moto aioboto3"
        ) from None

    with mock_aws():
        yield


# ── time mock fixture ────────────────────────────────────────────────────────

@pytest.fixture
def time_mock() -> Any:
    """Yield a ``time-machine`` based time-travel fixture.

    Requires ``time-machine`` installed.

    Example::

        def test_expiry(client, time_mock):
            time_mock.move_to("2024-01-01")
            ...
    """
    try:
        import time_machine
    except ImportError:
        raise ImportError(
            "The ``time_mock`` fixture requires ``time-machine``. "
            "Install it with: pip install time-machine"
        ) from None

    yield time_machine
