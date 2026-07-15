from __future__ import annotations

from rivex import Rivex, TestClient
from rivex.core.dependencies import Depends


async def real_db() -> str:
    return "real-db"


async def mock_db() -> str:
    return "mock-db"


def test_override_dependency_convenience():
    app = Rivex()
    app.override_dependency(real_db, mock_db)
    assert app.dependency_overrides[real_db] is mock_db
    app.clear_overrides()
    assert real_db not in app.dependency_overrides


def test_override_scope_restores():
    app = Rivex()
    app.override_dependency(real_db, mock_db)
    with app.override_scope({}):
        assert app.dependency_overrides[real_db] is mock_db
    assert app.dependency_overrides[real_db] is mock_db
    app.clear_overrides()


def test_override_scope_temporary():
    app = Rivex()

    async def alt_mock() -> str:
        return "alt-mock"

    app.override_dependency(real_db, mock_db)
    with app.override_scope({real_db: alt_mock}):
        assert app.dependency_overrides[real_db] is alt_mock
    assert app.dependency_overrides[real_db] is mock_db
    app.clear_overrides()


def test_override_scope_empty():
    app = Rivex()
    with app.override_scope({}):
        pass
    assert len(app.dependency_overrides) == 0


def test_dependency_override_integration():
    app = Rivex()

    @app.get("/db")
    async def get_db(db: str = Depends(real_db)):
        return {"db": db}

    app.override_dependency(real_db, mock_db)
    client = TestClient(app)
    resp = client.get("/db")
    assert resp.json()["db"] == "mock-db"


def test_testing_fixtures_app():
    from rivex.testing.testing_fixtures import app as fx_app

    assert callable(fx_app)


def test_testing_fixtures_client():
    from rivex.testing.testing_fixtures import client as fx_client

    assert callable(fx_client)


def test_cli_test_command_import():
    from rivex.cli.cli import _run_test
    assert callable(_run_test)
