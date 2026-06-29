# WebSockets

Rivex serves WebSockets through the same Rust core that handles HTTP. Each connection runs on its own thread with its own event loop, so a slow client never blocks the others.

## A WebSocket handler

Register a handler with `@app.websocket(path)` and take a `WebSocket` parameter. Call `accept()` to complete the handshake, then send and receive.

```python
from rivex import Rivex, WebSocket

app = Rivex()


@app.websocket("/ws")
async def ws_echo(ws: WebSocket):
    await ws.accept()
    while True:
        message = await ws.receive_text()
        if message is None:          # client closed the connection
            break
        await ws.send_text(f"echo: {message}")
```

## The WebSocket API

| Method | Description |
| --- | --- |
| `await ws.accept()` | Complete the handshake |
| `await ws.receive()` | Next message as `(kind, payload)`; `None` on close |
| `await ws.receive_text()` | Next text frame as `str` (or `None`) |
| `await ws.receive_bytes()` | Next binary frame as `bytes` |
| `await ws.receive_json()` | Receive a text frame and parse JSON |
| `await ws.send_text(s)` | Send a text frame |
| `await ws.send_bytes(b)` | Send a binary frame |
| `await ws.send_json(obj)` | Serialize and send as a text frame |
| `await ws.close(code=1000, reason="")` | Close the connection |

A `WebSocket` is also an async iterator, which makes the receive loop concise:

```python
@app.websocket("/chat")
async def chat(ws: WebSocket):
    await ws.accept()
    async for kind, payload in ws:
        if kind == "text":
            await ws.send_text(payload.upper())
```

When the peer disconnects mid-handler, Rivex raises `WebSocketDisconnect` (importable from `rivex`); catch it to run cleanup.

## Broadcasting with ConnectionManager

`ConnectionManager` (from `rivex.ws`) tracks connections and supports room-based broadcast — the backbone of chat and live-update features.

```python
from rivex import Rivex, WebSocket, WebSocketDisconnect
from rivex.ws import ConnectionManager

app = Rivex()
manager = ConnectionManager()


@app.websocket("/rooms/{room}")
async def room(ws: WebSocket, room: str):
    await manager.connect(ws, rooms=[room])
    try:
        while True:
            text = await ws.receive_text()
            if text is None:
                break
            await manager.send_json_to_room(room, {"room": room, "text": text})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
```

Trigger a broadcast from an ordinary HTTP route — useful for server-initiated notifications:

```python
@app.post("/rooms/{room}/announce")
async def announce(room: str, message: str):
    await manager.send_to_room(room, message)
    return {"sent": True}
```

### ConnectionManager methods

| Method | Description |
| --- | --- |
| `await connect(ws, rooms=None)` | Accept and optionally join rooms |
| `disconnect(ws)` | Remove from all rooms |
| `await broadcast(text)` / `broadcast_json(obj)` | Send to every connection |
| `await send_to_room(room, text)` / `send_json_to_room(room, obj)` | Send to one room |
| `join_room(ws, room)` / `leave_room(ws, room)` | Adjust membership |
| `active_connections` | Current connection count |
| `rooms()` | List of room names |

## Testing WebSockets

The in-process `TestClient` connects without a live server:

```python
from rivex import TestClient

client = TestClient(app)

with client.websocket_connect("/ws") as ws:
    ws.send_text("hello")
    assert ws.receive_text() == "echo: hello"
```

## Next

**Background Tasks & Concurrency** covers deferred work and how to offload blocking code from the worker threads.
