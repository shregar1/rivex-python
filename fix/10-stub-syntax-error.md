# rivex_core stub has syntax error at line 334

**Severity:** HIGH
**File:** `stubs/rivex_core/__init__.pyi` (line 334)
**Installed at:** `site-packages/rivex_core/__init__.pyi` (line 334)
**Affects:** mypy, pyright, any type checker that consumes the stub

## Problem

The `rivex_core` type stub has a syntax error at line 334: an unclosed
parenthesis in `def jsonable_encoder_py(`. This makes the file unparseable
as Python, which means:

- `mypy` reports "1 error in 1 file (errors prevented further checking)"
  and aborts the run
- `pyright` reports the same
- IDE type-checking on any file that imports `rivex_core` is broken

### Verification

```python
import ast
with open("site-packages/rivex_core/__init__.pyi") as f:
    src = f.read()
try:
    ast.parse(src)
except SyntaxError as e:
    print(f"SyntaxError at line {e.lineno}: {e.msg}")
    print(f"Text: {e.text!r}")
# → SyntaxError at line 334: '(' was never closed
# → Text: 'def jsonable_encoder_py('
```

The source stub at `stubs/rivex_core/__init__.pyi` (443 lines) does NOT
contain `jsonable_encoder_py` at all, but the installed stub (740 lines)
has it at line 334 — and at line 335 too, which is even more confusing.
This suggests the function was added in a build/release but the
generation script duplicated it and produced a broken file.

### Reproduce

```bash
pip install rivex
mypy --strict src/
# → 1 error: SyntaxError at line 334: '(' was never closed
```

Or directly:

```bash
python -c "import ast; ast.parse(open('$(python -c \"import rivex_core; print(rivex_core.__file__)\")').read())"
# → SyntaxError: '(' was never closed (line 334)
```

## Impact

- **Type checking completely broken** for any project that uses rivex.
  No way to enable mypy strict mode.
- **IDE autocomplete / type hints degraded** — falls back to `Any`
  for all `rivex_core` symbols.
- **CI integration** — if you add a mypy step to CI, it fails before
  reporting any of your code's type errors.

## Fix

Two issues to address:

1. Remove the duplicate `def jsonable_encoder_py(` declarations at
   lines 334 and 335. The file should have the function declared ONCE
   with proper signature and body.

2. Identify why the installed stub (740 lines) diverges from the
   source stub (443 lines). There's likely a stub generation script
   that's adding non-stub content or duplicating function declarations.

A correct version of the function should look like:

```python
def jsonable_encoder_py(
    value: Any,
    include: Optional[list[str]] = ...,
    exclude: Optional[list[str]] = ...,
    exclude_none: bool = ...,
) -> Any: ...
```

(Single declaration, complete parameters, return type, body placeholder.)
