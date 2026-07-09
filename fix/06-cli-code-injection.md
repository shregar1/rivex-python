# CLI Dev Reload Has Code Injection Vulnerability

**Severity:** HIGH
**File:** `src/rivex/cli.py:369-375`

## Problem

The `_run_with_reload` function constructs a Python command using f-string interpolation of user-provided values:

```python
cmd = (
    f'import sys; sys.path.insert(0, "."); '
    f"from {module_part} import {app_path}; "
    f"app.run(host='{host}', port={port})"
)
```

If `host`, `port`, or `module_part` contain shell metacharacters or Python code delimiters, arbitrary code execution is possible.

## Impact

- `rivex dev "main; import os; os.system('evil'):app"` executes arbitrary code
- Any untrusted input to the dev command is a vector

## Fix

Use `shlex.quote()` for shell arguments or pass values as properly separated arguments rather than string interpolation. Use `subprocess.run([...])` with a list of arguments instead of a shell string.
