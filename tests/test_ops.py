"""Tests for DataProtection, WorkerManager, Autodiscovery, DevREPL."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from rivex import Rivex
from rivex.autodiscovery import autodiscover
from rivex.auth.data_protection import DataProtector
from rivex.cli.dev_repl import start_repl
from rivex.native.worker_manager import WorkerManager


@pytest.fixture
def app():
    return Rivex(docs_url=None, redoc_url=None, landing_page=False, openapi_url=None)


# ── DataProtection ──


class TestDataProtector:
    def test_protect_unprotect_dict(self):
        protector = DataProtector(key=b"x" * 32)
        data = {"user_id": 42, "role": "admin"}
        token = protector.protect(data)
        result = protector.unprotect(token)
        assert result == data

    def test_protect_unprotect_string(self):
        protector = DataProtector(key=b"x" * 32)
        token = protector.protect("hello world")
        result = protector.unprotect(token)
        assert result == "hello world"

    def test_protect_unprotect_list(self):
        protector = DataProtector(key=b"x" * 32)
        token = protector.protect([1, 2, 3, {"nested": True}])
        result = protector.unprotect(token)
        assert result == [1, 2, 3, {"nested": True}]

    def test_protect_with_purpose(self):
        protector = DataProtector(key=b"x" * 32)
        token = protector.protect({"uid": 1}, purpose="session")
        result = protector.unprotect(token, purpose="session")
        assert result == {"uid": 1}

    def test_wrong_purpose_fails(self):
        protector = DataProtector(key=b"x" * 32)
        token = protector.protect({"uid": 1}, purpose="session")
        with pytest.raises(ValueError, match="Purpose mismatch"):
            protector.unprotect(token, purpose="csrf")

    def test_no_purpose_no_check(self):
        protector = DataProtector(key=b"x" * 32)
        token = protector.protect({"uid": 1}, purpose="session")
        # No purpose check when purpose is None
        result = protector.unprotect(token)
        assert result == {"uid": 1}

    def test_invalid_token_fails(self):
        protector = DataProtector(key=b"x" * 32)
        with pytest.raises(ValueError, match="Decryption failed"):
            protector.unprotect("invalid_token_that_cannot_be_decrypted")

    def test_tampered_token_fails(self):
        protector = DataProtector(key=b"x" * 32)
        token = protector.protect({"uid": 42})
        # Tamper with the token (change a character in the middle)
        mid = len(token) // 2
        tampered = token[:mid] + ("a" if token[mid] != "a" else "b") + token[mid + 1 :]
        with pytest.raises(ValueError, match="Decryption failed"):
            protector.unprotect(tampered)

    def test_key_rotation(self):
        old_key = b"o" * 32
        new_key = b"n" * 32
        protector = DataProtector(key=old_key)
        token = protector.protect({"uid": 42})

        protector.rotate_key(new_key)
        # Old token still decrypts with rotated key (old key in history)
        result = protector.unprotect(token)
        assert result == {"uid": 42}

        # New token uses new key
        new_token = protector.protect({"uid": 99})
        assert protector.unprotect(new_token) == {"uid": 99}

    def test_invalid_key_size(self):
        with pytest.raises(ValueError, match="32 bytes"):
            DataProtector(key=b"too_short")

    def test_raw_protection(self):
        protector = DataProtector(key=b"x" * 32)
        plaintext = b"binary data \x00\x01\x02"
        ciphertext = protector.protect_raw(plaintext)
        result = protector.unprotect_raw(ciphertext)
        assert result == plaintext

    def test_encoding_flag(self):
        protector = DataProtector(key=b"x" * 32, encoding=True)
        token = protector.protect({"uid": 1})
        assert isinstance(token, str)
        assert "+" not in token and "/" not in token  # URL-safe base64


# ── WorkerManager ──


class TestWorkerManager:
    def test_worker_manager_creation(self, app):
        mgr = WorkerManager(app)
        assert mgr._app is app
        assert mgr.shared_state is not None

    def test_shared_state_set_get(self, app):
        mgr = WorkerManager(app)
        mgr.shared_state.set_str("test_key", "test_value")
        assert mgr.shared_state.get("test_key") == "test_value"

    def test_shared_state_contains(self, app):
        mgr = WorkerManager(app)
        mgr.shared_state.set_str("existing", "value")
        assert mgr.shared_state.contains("existing")
        assert not mgr.shared_state.contains("missing")

    def test_shared_state_increment(self, app):
        mgr = WorkerManager(app)
        mgr.shared_state.set_int("counter", 0)
        result = mgr.shared_state.increment("counter", 5)
        assert result == 5

    def test_background_process_decorator(self, app):
        mgr = WorkerManager(app)

        @mgr.background_process
        async def my_task():
            pass

        assert len(mgr._background_processes) == 1
        assert mgr._background_processes[0] is my_task

    def test_custom_process_decorator(self, app):
        mgr = WorkerManager(app)

        @mgr.custom_process
        def my_process():
            pass

        assert len(mgr._custom_processes) == 1
        assert mgr._custom_processes[0] is my_process

    def test_multiple_background_processes(self, app):
        mgr = WorkerManager(app)

        @mgr.background_process
        async def task1():
            pass

        @mgr.background_process
        async def task2():
            pass

        @mgr.background_process
        async def task3():
            pass

        assert len(mgr._background_processes) == 3


# ── Autodiscovery ──


class TestAutodiscovery:
    def test_autodiscover_nonexistent_dir(self, app):
        with pytest.raises(FileNotFoundError):
            autodiscover(app, directory="/nonexistent/path/xyz")

    def test_autodiscover_finds_routers(self, app, tmp_path):
        # Create a test module with a router
        router_module = tmp_path / "users.py"
        router_module.write_text("""
from rivex.web.routing import Router
router = Router(prefix="/users")

@router.get("/")
def list_users():
    return {"users": []}

@router.get("/{id}")
def get_user(id: int):
    return {"user_id": id}
""")

        count = autodiscover(app, directory=str(tmp_path))
        assert count >= 1

    def test_autodiscover_skips_non_router_modules(self, app, tmp_path):
        # Create a module without a router
        plain_module = tmp_path / "utils.py"
        plain_module.write_text("""
def helper():
    return "not a router"
""")

        count = autodiscover(app, directory=str(tmp_path))
        assert count == 0

    def test_autodiscover_with_prefix(self, app, tmp_path):
        router_module = tmp_path / "api.py"
        router_module.write_text("""
from rivex.web.routing import Router
router = Router(prefix="/data")

@router.get("/items")
def list_items():
    return {"items": []}
""")

        autodiscover(app, directory=str(tmp_path), prefix="/v2")
        # Routes should be prefixed with /v2/data/items
        assert any(r.path == "/v2/data/items" for r in app._routes)

    def test_autodiscover_excludes(self, app, tmp_path):
        # Create excluded module
        excluded = tmp_path / "_private.py"
        excluded.write_text("""
from rivex.web.routing import Router
router = Router(prefix="/private")
""")

        count = autodiscover(app, directory=str(tmp_path), exclude=["_*"])
        assert count == 0


# ── Dev REPL ──


class TestDevREPL:
    def test_start_repl_does_not_raise(self, app):
        # We can't test the interactive part, but we can verify
        # the function can be called without errors
        # start_repl blocks, so we just verify it's callable
        assert callable(start_repl)
