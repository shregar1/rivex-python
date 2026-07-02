# `app.py` from third-party editable installs shadows user `app/` packages

**Severity:** HIGH (blocks proper `app/` package usage)
**Files affected:** any project with a local `app/` package + the
`rivex` SDK installed alongside certain editable installs.

## Problem

When you have a local Python package named `app/` (e.g. `src/app/`)
and `app.py` exists at any site-packages level on `sys.path`, the
single `app.py` module wins over the package directory. This silently
shadows your `app/` package.

For projects using the `rivex` SDK (which lives in
`/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages/`),
this becomes a problem when the system has an editable install of any
package that ships a top-level `app.py` — for example, FastX MVC
channels (`fastx_channels-1.7.0.dist-info`) installs
`/__editable__.fastx_channels-1.7.0.pth` pointing to
`/Users/shreyansh/Documents/projects/fastmvc/fastx_channels/src`,
which contains a top-level `app.py`.

### Reproduce

```python
import sys
# Default site-packages order
import app  # → this is the FastX app.py from fastx_channels
print(app.__file__)
# → /Users/shreyansh/Documents/projects/fastmvc/fastx_channels/src/app.py

# Now try to use a local app/ package
import sys
sys.path.insert(0, "/path/to/your/project/src")  # local app/ first
import app  # STILL the FastX app.py wins
print(app.__file__)
# → /Users/shreyansh/Documents/projects/fastmvc/fastx_channels/src/app.py
```

The local `app/` package directory is shadowed by the .pth-installed
`app.py` because `.pth` files are processed AFTER user `sys.path`
manipulation in many cases.

## Impact

- **Wick:** During development we hit `ImportError: cannot import name
  '_extract_key' from 'app.key_manager'` because `app.py` from
  fastx_channels was being imported instead of our `src/app/`
  package. The workaround is to:
  1. Place the local package on `sys.path` BEFORE site-packages
  2. Use unique package names (e.g. `wick/` instead of `app/`)
  3. Use editable install so the local package is registered properly

- **Any project** that names their top-level package `app` and runs in
  the same Python environment as a FastX install (or any other
  editable install that ships an `app.py`) is silently broken.

## Fix

The `rivex` SDK itself should not ship a top-level `app.py` if it
includes an `app/` package (e.g. via the `rivex-admin` or
`rivex-monitor` sub-packages). Currently, the `app.py` problem comes
from TRANSITIVE dependencies (fastx_channels), not rivex itself, but
the symptom is identical from a user perspective.

Recommended actions:

1. **Audit `app.py` at site-packages** when imports break: run
   `python -c "import app; print(app.__file__)"` to see which `app` is
   being loaded. If it's not yours, that's the bug.

2. **Avoid the name `app`** in your top-level package if you control
   the project. Names like `myapp/`, `backend/`, or domain-specific
   names (`wick/`) avoid the entire class of conflict.

3. **Pin a unique top-level** — if you must use a generic name, use
   `__editable__.your_app-X.Y.Z.pth` and verify the `app.py` path
   resolution manually after `pip install -e .`.

4. **Add a CI sanity check** — `python -c "import app; assert
   app.__file__.startswith('src/'), 'app is shadowed by ' +
   app.__file__"` — to catch shadowing in CI before shipping.
