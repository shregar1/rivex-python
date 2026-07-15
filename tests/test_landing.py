"""Tests for the bare-bones landing page served at ``GET /``.

When the user installs only the bare ``rivex`` package (no admin
plugin, no codegen, no scaffold) and creates a ``Rivex()`` with no
routes, hitting ``GET /`` should serve a friendly HTML page that
tells them the server is up, lists any routes they've registered,
and points them at the next step (define a route, install an
admin, etc.).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _load_landing():
    name = "rivex_landing_under_test"
    spec = importlib.util.spec_from_file_location(
        name,
        Path(__file__).resolve().parents[1] / "src" / "rivex" / "web" / "_landing.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_landing_html_contains_app_identity():
    landing = _load_landing()

    class _FakeApp:
        title = "Acme API"
        version = "2.4.1"
        description = "Production-ready REST API"
        app_name = "Acme"
        powered_by = "Acme Cloud"
        admin_url = None
        _routes = []

    body, content_type = landing.build_landing_page(_FakeApp())  # type: ignore[arg-type]
    assert content_type == "text/html; charset=utf-8"
    assert "<!DOCTYPE html>" in body
    assert "Acme API" in body
    assert "2.4.1" in body
    assert "Acme" in body
    assert "Acme Cloud" in body  # powered_by


def test_landing_lists_routes():
    landing = _load_landing()

    class _Record:
        def __init__(self, method, path, handler="handler"):
            self.method = method
            self.path = path
            self.endpoint = type("E", (), {"__name__": handler})

    class _FakeApp:
        title = "T"
        version = "0.0.1"
        description = None
        app_name = "T"
        powered_by = None
        admin_url = None
        _routes = [
            _Record("GET", "/items"),
            _Record("POST", "/items"),
            _Record("GET", "/items/{id}"),
        ]

    body, _ = landing.build_landing_page(_FakeApp())  # type: ignore[arg-type]
    assert "GET" in body
    assert "POST" in body
    assert "/items" in body
    assert "/items/{id}" in body
    assert "3 routes" in body


def test_landing_handles_no_routes():
    landing = _load_landing()

    class _FakeApp:
        title = "T"
        version = "0.0.1"
        description = None
        app_name = "T"
        powered_by = None
        admin_url = None
        _routes = []

    body, _ = landing.build_landing_page(_FakeApp())  # type: ignore[arg-type]
    # No "Powered by" since powered_by is None
    assert "Powered by" not in body
    # Mentions defining a route
    assert "@app.get" in body
    # Singular form (1 route → still 0 here so plurals work)
    assert "0 routes" in body or "no routes" in body.lower()


def test_landing_html_escapes_user_supplied_values():
    """XSS: app title with HTML chars must be escaped."""
    landing = _load_landing()

    class _FakeApp:
        title = "<script>alert(1)</script>"
        version = "0.0.1"
        description = None
        app_name = "X"
        powered_by = None
        admin_url = None
        _routes = []

    body, _ = landing.build_landing_page(_FakeApp())  # type: ignore[arg-type]
    # The raw <script> tag must NOT appear in the page
    assert "<script>alert(1)</script>" not in body
    # The escaped version DOES
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_landing_suggests_admin_when_not_mounted():
    landing = _load_landing()

    class _FakeApp:
        title = "T"
        version = "0.0.1"
        description = None
        app_name = "T"
        powered_by = None
        admin_url = None
        _routes = []

    body, _ = landing.build_landing_page(_FakeApp())  # type: ignore[arg-type]
    assert "admin" in body.lower()
    assert "createsuperuser" in body or "admin_url" in body


def test_landing_dark_mode_css_present():
    """The CSS includes a dark-mode media query for parity with the
    admin dashboard's stylesheet."""
    landing = _load_landing()

    class _FakeApp:
        title = "T"
        version = "0.0.1"
        description = None
        app_name = "T"
        powered_by = None
        admin_url = None
        _routes = []

    body, _ = landing.build_landing_page(_FakeApp())  # type: ignore[arg-type]
    assert "prefers-color-scheme: dark" in body


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
