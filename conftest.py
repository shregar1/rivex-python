"""Top-level conftest for the ``rivex`` test suite.

Pytest 8 warns about ``collect_ignore`` being set via ``ini_options``; the
canonical place is a root-level conftest, so the skip-list lives here.

The ``rivex_scaffold/template`` and ``mvc`` directories both ship their
own ``tests/`` folders that contain files with colliding module names
(e.g. ``test_items_dtos``). Those directories are example projects, not
part of the framework test suite, so we tell pytest to skip them.
"""

collect_ignore = [
    "rivex_scaffold/template",
    "mvc",
    # The end-to-end demo test exercises ``_run_demo.py``, a one-off
    # working file that lived at the repo root while the landing /
    # admin pages were being developed. The demo file is not part of
    # the shipped package, so we skip its dedicated test file rather
    # than keep both the demo and the test in lockstep.
    "tests/test_e2e_demo.py",
]
