# WebSocket Constructor Signature Mismatch

**Severity:** HIGH
**Files:** `src/rivex/websocket.py:23-28` vs `src/rivex/applications.py:1223-1228`

## Problem

`websocket.py` defines:

```python
class WebSocket:
    def __init__(self, scope, reader, writer):  # 3 args
```

But `ws_wrapper` in `applications.py` calls:

```python
ws = WebSocket(raw_ws)  # 1 arg (only scope dict)
```

Meanwhile `websockets.py` (used by the ASGI path) has:

```python
class WebSocket:
    def __init__(self, raw):  # 1 arg — matches
```

## Impact

- `websocket.py` appears to be dead/incorrect code
- The native engine's WebSocket path either crashes on init or uses the wrong module entirely
- WebSocket support via the native Rust engine is broken

## Fix

Determine whether `websocket.py` or `websockets.py` is the intended module, then either:
- Update the constructor signature to match the call site
- Or ensure `ws_wrapper` imports from the correct module
