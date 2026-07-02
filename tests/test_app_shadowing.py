"""Smoke test: verify the rivex package itself is importable and not shadowed.

Background — see fix/11-app-py-shadowing.md. Third-party editable
installs (notably ``fastx_channels``) can drop a top-level ``app.py``
onto ``sys.path`` and silently shadow a user's local ``app/`` package.
This test guards against a similar problem inside the rivex SDK
itself: if the SDK ever ships a top-level ``app.py`` (e.g. via a
sub-package), users with a local ``app/`` package will have their
imports broken.

The check is intentionally narrow: it only asserts that
``import rivex`` resolves to the package directory, not a stray
``rivex.py`` file at the same level.
"""
from __future__ import annotations

import importlib
import pathlib
import sys


def test_rivex_is_a_package_not_a_module() -> None:
    spec = importlib.util.find_spec("rivex")
    assert spec is not None, "rivex is not importable at all"
    assert spec.submodule_search_locations is not None, (
        "rivex resolves to a single .py file rather than a package — "
        "this can shadow user 'rivex.*' imports. Convert rivex.py to "
        "a rivex/ package directory."
    )


def test_no_top_level_app_module_in_sdk() -> None:
    """The SDK must not ship a top-level ``app.py`` / ``app/`` package.

    A project that names its top-level package ``app`` (very common)
    would have it shadowed by the SDK's module of the same name. If
    this test ever fails, rename the SDK-internal module to something
    project-unique (e.g. ``rivex_admin.app`` instead of ``app``).
    """
    pkg_root = pathlib.Path(__file__).resolve().parent.parent / "src" / "rivex"
    candidates = list(pkg_root.glob("app.py")) + list((pkg_root / "app").glob("*.py")) if (pkg_root / "app").is_dir() else list(pkg_root.glob("app.py"))
    assert not candidates, (
        f"rivex SDK ships a top-level 'app' module/package: {candidates}. "
        f"This will shadow user 'app/' packages — rename to a project-"
        f"unique name like 'rivex_admin.app' or 'rivex_app'."
    )


def test_import_does_not_mutate_sys_path() -> None:
    """Importing rivex must not permanently insert '.', './src', etc. into sys.path."""
    before = list(sys.path)
    # Force a fresh import
    for mod in list(sys.modules):
        if mod == "rivex" or mod.startswith("rivex."):
            del sys.modules[mod]
    import rivex  # noqa: F401
    after = list(sys.path)
    # The only allowed additions are paths that resolve to the
    # actual rivex install location, not relative entries like ".".
    new = [p for p in after if p not in before]
    bad = [p for p in new if p in ("", ".") or p.startswith("./")]
    assert not bad, f"import rivex inserted relative paths into sys.path: {bad}"
