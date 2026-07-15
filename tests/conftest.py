"""Test conftest for the ``rivex`` package.

The compiled ``rivex_core`` extension is expected to be installed in
the active Python environment — the wheel ships it as part of the
distribution, and the test suite is designed to exercise the real
binary end-to-end.  We deliberately do **not** stub the extension
in tests: any call into ``rivex_core`` should reach the Rust
implementation, and the tests are the contract that proves the
Python wrapper drives the binary correctly.

If the binary isn't installed, the existing conftest is responsible
for raising a clear ``ImportError`` at import time (driven by the
``try / import rivex_core as _rc`` blocks in the public modules).
This conftest only sets up the few cross-test fixtures we need.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _restore_rivex_module_identity():
    """Snapshot and restore the ``rivex`` module across every test.

    Some tests (notably ``tests/test_barebones.py``) exercise
    "minimal install" code paths by ``sys.modules.pop("rivex", None)``
    and re-importing the package.  When the re-imported package
    lands in a different interpreter state than the one other tests
    imported, classes created against the original (e.g. an
    ``AuditPlugin(Plugin)`` subclass defined in ``test_e2e_full.py``)
    fail ``isinstance`` checks against the new ``Plugin`` class
    object, surfacing as cryptic
    "Expected Plugin instance, got <class …>" errors.

    Snapshotting the relevant modules before each test and restoring
    them on teardown keeps the rest of the suite seeing a stable
    ``rivex`` module identity.
    """
    saved = {
        name: mod
        for name, mod in sys.modules.items()
        if name == "rivex" or name.startswith("rivex.")
    }
    # Snapshot the custom-body-schema registries too.  A handful of
    # tests call ``rivex._bodies.register_body_schema(...)`` to plug
    # in their own backend; the per-test ``finally`` cleanup only
    # removes the specific name that test added, but other tests
    # still register detectors that end up shadowing one another
    # when the suite runs as a whole.  Resetting both lists around
    # every test keeps the registries empty unless a test
    # intentionally fills them.
    from rivex.core import _bodies as _rb

    saved_handlers = dict(_rb._CUSTOM_HANDLERS)
    saved_detectors = list(_rb._CUSTOM_DETECTORS)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name == "rivex" or name.startswith("rivex."):
                sys.modules.pop(name, None)
        sys.modules.update(saved)
        for pkg in ("rivex_admin", "rivex_codegen", "rivex_scaffold"):
            sys.modules.pop(pkg, None)
        _rb._CUSTOM_HANDLERS.clear()
        _rb._CUSTOM_HANDLERS.update(saved_handlers)
        _rb._CUSTOM_DETECTORS[:] = saved_detectors
