"""Top-level compatibility shim for the bundled Rust core.

The compiled PyO3 extension is shipped *inside* the ``rivex`` wheel as
``rivex.rivex_core`` (maturin requires the native module to live within the
distribution's Python package). This module re-binds the import name
``rivex_core`` to that same extension object, so existing call sites that do
``import rivex_core`` resolve to the bundled binary — there is no separate
``rivex-core`` package to install.

The shim loads the compiled module by absolute file path so that the import
does not trigger ``rivex/__init__.py`` (which transitively re-imports
``rivex_core`` via ``rivex._rust``). Loading by file path keeps the
``rivex`` package importable without a circular-import error.
"""
import glob
import importlib.util
import os
import sys

_dir = os.path.dirname(os.path.abspath(__file__))
_so_dir = os.path.join(_dir, "rivex")
_matches = glob.glob(os.path.join(_so_dir, "rivex_core.*.so"))
if not _matches:
    raise ImportError(f"No rivex_core native extension found in {_so_dir}")
_so_path = _matches[0]
_spec = importlib.util.spec_from_file_location("rivex_core", _so_path)
_core = importlib.util.module_from_spec(_spec)
sys.modules["rivex_core"] = _core
_spec.loader.exec_module(_core)
