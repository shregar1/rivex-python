# Dead code: `len(self._handlers)` no-op in ASGIAdapter._build

**Severity:** LOW (cosmetic / dead code)
**File:** `src/rivex/asgi.py:64`

## Problem

In `ASGIAdapter._build()`:

```python
def _build(self) -> None:
    if self._built:
        return
    self._built = True
    # ...
    for record in self._app._routes:
        # ...
        handler = self._apply_middleware(wrapper)
        len(self._handlers)        # ← NO-OP: computes length and discards it
        self._handlers.append(handler)
        # ...
```

`len(self._handlers)` is a dead expression. It computes the current
length of `self._handlers` and immediately discards the result. It has
no side effect and serves no purpose.

This is clearly a debugging leftover — someone was likely inspecting
the list length during development and forgot to remove the statement.

### Why it matters

- Suggests the code was written under time pressure or without review
- Indicates that tests in this file may not cover the route-registration
  path
- Slight readability cost — readers spend cognitive effort wondering
  what the statement is for
- The `_handlers` list is being populated via `.append()` AFTER the
  no-op, suggesting the order is intentional (no relationship)

## Fix

Delete the line:

```python
def _build(self) -> None:
    if self._built:
        return
    self._built = True
    # ...
    for record in self._app._routes:
        # ...
        handler = self._apply_middleware(wrapper)
        self._handlers.append(handler)  # no no-op
        # ...
```

## Note

The `try/except ValueError: pass` block at lines 67-69 silently swallows
route registration errors. This is a separate but related issue:
adding a duplicate route should raise or log, not be ignored.

```python
try:
    self._asgi_router.add_route(record.method, record.path, handler)
except ValueError:
    pass  # ← swallowed
```

The C router (and most web frameworks) raise on duplicate route
registration. Silently ignoring this can lead to bugs where a route
appears registered but actually isn't.
