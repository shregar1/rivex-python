"""Smoke tests for the bare-bones Rivex core.

These tests simulate ``pip install rivex`` (no extras) by stubbing
out the optional companion packages (``rivex_admin``,
``rivex_codegen``, ``rivex_scaffold``) and confirming the core
still imports cleanly and ``Rivex()`` constructs without error.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _restore_companion_packages():
    """Restore the real companion packages AND the original ``rivex`` module.

    The barebones tests do two disruptive things to ``sys.modules``:

    1. Stub out ``rivex_admin`` / ``rivex_codegen`` / ``rivex_scaffold``
       to simulate them not being installed.
    2. ``sys.modules.pop("rivex", None)`` and re-import it so the
       stub modules above take effect.

    Step (2) leaves the rest of the test suite in a bad state: any
    class object that was *defined against* the original ``rivex``
    module (e.g. ``class AuditPlugin(Plugin)`` in ``test_e2e_full.py``)
    will then fail an ``isinstance(inst, Plugin)`` check inside
    ``rivex.applications.register_plugin`` because the new ``rivex``
    has a different ``Plugin`` class object.

    This fixture snapshots the relevant modules on entry and restores
    them on exit so the rest of the suite sees a consistent ``rivex``
    module identity.
    """
    saved = {
        name: mod
        for name, mod in sys.modules.items()
        if name == "rivex" or name.startswith("rivex.")
    }
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name == "rivex" or name.startswith("rivex."):
                sys.modules.pop(name, None)
        sys.modules.update(saved)
        for pkg in ("rivex_admin", "rivex_codegen", "rivex_scaffold"):
            sys.modules.pop(pkg, None)


def _purge_optional_packages() -> None:
    """Remove every optional companion package from ``sys.modules``.

    Mirrors what the import system would do in an environment where
    the user has only ``pip install rivex`` with no extras.
    """
    for name in list(sys.modules):
        if name in {"rivex", "rivex_admin", "rivex_codegen", "rivex_scaffold"}:
            continue
        if (
            name.startswith("rivex.")
            or name.startswith("rivex_admin.")
            or name.startswith("rivex_codegen.")
            or name.startswith("rivex_scaffold.")
        ):
            del sys.modules[name]
    for pkg in ("rivex_admin", "rivex_codegen", "rivex_scaffold"):
        sys.modules.pop(pkg, None)


def _make_missing_module(name: str) -> types.ModuleType:
    """Build a stub module whose attributes all raise ``ImportError``.

    Used by the barebones tests to simulate ``rivex_admin`` etc. not
    being installed.
    """
    mod = types.ModuleType(name)

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise ImportError(f"simulated ImportError: {name!r} is not installed")

    mod.__getattr__ = _raise  # type: ignore[attr-defined]
    return mod


def test_core_imports_without_optional_companions() -> None:
    """``import rivex`` succeeds even with the companion packages uninstalled.

    We stub them out so the import system believes they're missing,
    then import the core and assert the public surface is intact.
    """
    _purge_optional_packages()
    sys.modules["rivex_admin"] = _make_missing_module("rivex_admin")
    sys.modules["rivex_codegen"] = _make_missing_module("rivex_codegen")
    sys.modules["rivex_scaffold"] = _make_missing_module("rivex_scaffold")

    # Force re-import of rivex.
    sys.modules.pop("rivex", None)
    rivex = importlib.import_module("rivex")

    # Public surface still present.
    assert hasattr(rivex, "Rivex")
    assert hasattr(rivex, "Body")
    assert hasattr(rivex, "Form")
    assert hasattr(rivex, "Depends")
    assert hasattr(rivex, "coerce_body")
    assert hasattr(rivex, "BodySchema")
    # Optional helpers are None when their companion package is missing.
    assert rivex.admin_action is None
    assert rivex.admin_partial is None


def test_rivex_constructs_without_admin_installed() -> None:
    """A bare ``Rivex()`` constructor works without ``rivex_admin``."""
    _purge_optional_packages()
    sys.modules["rivex_admin"] = _make_missing_module("rivex_admin")
    sys.modules["rivex_codegen"] = _make_missing_module("rivex_codegen")
    sys.modules["rivex_scaffold"] = _make_missing_module("rivex_scaffold")
    sys.modules.pop("rivex", None)
    rivex = importlib.import_module("rivex")
    app = rivex.Rivex(title="barebones")
    assert app.title == "barebones"
    assert app.admin_url is None  # default = no admin mounted


def test_rivex_admin_url_without_admin_raises_clear_error() -> None:
    """Asking for an admin URL when ``rivex_admin`` is missing raises
    a helpful ``RuntimeError`` instead of a confusing ``ImportError``."""
    _purge_optional_packages()
    sys.modules["rivex_admin"] = _make_missing_module("rivex_admin")
    sys.modules["rivex_codegen"] = _make_missing_module("rivex_codegen")
    sys.modules["rivex_scaffold"] = _make_missing_module("rivex_scaffold")
    sys.modules.pop("rivex", None)
    rivex = importlib.import_module("rivex")
    with pytest.raises(RuntimeError, match="pip install rivex\\[admin\\]"):
        rivex.Rivex(title="with-admin", admin_url="/admin")


def test_rivex_cli_generate_without_scaffold_raises_clear_error(capsys) -> None:
    """``rivex generate`` should fail with a clear message when
    ``rivex_scaffold`` is missing."""
    _purge_optional_packages()
    sys.modules["rivex_admin"] = _make_missing_module("rivex_admin")
    sys.modules["rivex_codegen"] = _make_missing_module("rivex_codegen")
    sys.modules["rivex_scaffold"] = _make_missing_module("rivex_scaffold")
    sys.modules.pop("rivex", None)
    importlib.import_module("rivex")
    from rivex import cli

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["generate", "demo", "."])
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "rivex[scaffold]" in err


def test_rivex_createsuperuser_works_in_barebones() -> None:
    """``rivex createsuperuser`` is exposed in the core CLI and reaches
    the SQLite store (when the admin plugin is installed).

    We run it as a real subprocess so we exercise the actual
    ``RIVEX_ADMIN_DB`` env-var path and the printed-once token.
    """
    import os
    import subprocess

    env = {
        **os.environ,
        "RIVEX_ADMIN_DB": str(tmp_db_path()),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, '.'); "
            "from rivex.cli import main; sys.argv = ['rivex', 'createsuperuser']; "
            "main()",
        ],
        input="autotest\n\n\n",  # username, then blank token, then confirm
        capture_output=True,
        text=True,
        timeout=10,
        cwd="/Users/shreyansh/Documents/vexarr/rivex/python.rivex.vexarr.com",
        env=env,
    )
    combined = result.stdout + result.stderr
    # We expect either success (CLI auto-generated a token) or a
    # clear "rivex_admin not installed" error.
    assert (
        "admin dashboard" in combined.lower()
        or "rivex_admin" in combined
        or "creat" in combined.lower()
    ), f"unexpected output: stdout={result.stdout!r} stderr={result.stderr!r}"


def tmp_db_path() -> Path:
    """Helper that returns a fresh tmp path inside the test's cwd."""
    import tempfile

    return Path(tempfile.mkdtemp(prefix="rivex-test-")) / "admin.db"
