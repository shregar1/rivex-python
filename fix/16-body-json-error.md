# `Request.body_json()` raises unhelpful `JSONDecodeError` on invalid input

**Severity:** LOW
**File:** `src/rivex/requests.py:86-92`

## Problem

`Request.body_json()` parses the raw bytes body as JSON. If the body
is not valid JSON, the user gets a raw `json.JSONDecodeError` with
a position pointer but no context about WHICH request or which
endpoint failed:

```python
def body_json(self) -> Any:
    """Parse JSON body synchronously."""
    if not self._body:
        return None
    if HAS_CORE:
        return _rc.json_deserialize(self._body)
    return json.loads(self._body)  # ← raises bare JSONDecodeError
```

```python
# In a route handler
@app.post("/webhook")
async def webhook(request: Request):
    payload = request.body_json()  # ← raises JSONDecodeError
    # ...
```

When `payload = json.loads(b"not valid json")` fails, the user gets:

```
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

The error doesn't include:
- The HTTP method
- The path
- The body bytes (so the user can see WHAT was invalid)
- A way to distinguish "empty body" from "invalid JSON"

This makes debugging webhook handlers painful — you see a JSON
error but have to correlate stack traces with logs to find the
request that failed.

## Fix

Wrap the JSON decode in a request-aware error:

```python
def body_json(self) -> Any:
    """Parse JSON body. Raises a request-aware error on invalid input."""
    if not self._body:
        return None
    if HAS_CORE:
        try:
            return _rc.json_deserialize(self._body)
        except Exception as e:
            raise RequestBodyError(
                method=self.method,
                path=self.path,
                body_preview=self._body[:200],
                reason=str(e),
            ) from e
    try:
        return json.loads(self._body)
    except json.JSONDecodeError as e:
        raise RequestBodyError(
            method=self.method,
            path=self.path,
            body_preview=self._body[:200],
            reason=f"Invalid JSON at line {e.lineno} col {e.colno}: {e.msg}",
        ) from e
```

Where `RequestBodyError` is a custom exception that includes the
request context, so a 400 response can include all the necessary
debugging info.

## Note

A related but minor issue: `def form(self)` returns `dict[str, str]`
but the actual form data could be `dict[str, str | list[str]]` (for
repeated keys). The current signature lies about the return type.
