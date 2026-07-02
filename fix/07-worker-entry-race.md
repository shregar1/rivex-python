# `_async_worker_entry` Uses `_Rivex` Before Module-Level Assignment

**Severity:** HIGH
**File:** `src/rivex/applications.py:990,1003`

## Problem

`_async_worker_entry` performs `isinstance(app, _Rivex)` checks, but `_Rivex = Rivex` is assigned at module level on line 1804 — after the class body. This works at runtime due to Python's lazy evaluation of `isinstance` but is fragile.

Additionally, the class attribute `_Rivex_self = None` (line 1782, documented as "internal alias used by the multi-process supervisor") is never reassigned — pure dead code.

## Impact

- Fragile code that could break depending on import order
- Misleading `_Rivex_self` attribute confuses readers

## Fix

Move `_Rivex = Rivex` to before the class that uses it, or inline the isinstance check. Remove the dead `_Rivex_self` attribute.
