"""Type stub for the top-level ``rivex_core`` module.

``src/rivex_core.py`` is a runtime shim that loads the compiled PyO3
extension (``rivex/rivex_core.*.so``) dynamically via :mod:`importlib` and
rebinds it as the top-level ``rivex_core`` name, so ``import rivex_core``
keeps working. That dynamic loading cannot be introspected by type
checkers, so this sibling ``.pyi`` (which mypy/pyright prefer over the
``.py``) gives them a typed view of the same module.

The public API is identical to ``rivex.rivex_core`` — it is the very same
extension object — so this stub simply re-exports the comprehensive
declarations in ``src/rivex/rivex_core.pyi``.
"""

from rivex.rivex_core import *
