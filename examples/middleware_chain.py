import time
from itertools import count
from typing import Any

from rivex import CORSMiddleware, Middleware, RequestIdMiddleware, Rivex

app = Rivex(title="Middleware Chain Example")


class TimingMiddleware(Middleware):
    async def process(self, request_data: dict[str, Any], call_next):
        start = time.perf_counter()
        response = await call_next(request_data)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response["headers"] = response.get("headers", []) + [
            ("x-elapsed-ms", f"{elapsed_ms:.2f}"),
        ]
        method = request_data.get("method")
        path = request_data.get("path")
        print(f"[timing] {method} {path} -> {elapsed_ms:.2f}ms")
        return response


class RequestCounterMiddleware(Middleware):
    def __init__(self) -> None:
        self._counter = count(1)

    async def process(self, request_data: dict[str, Any], call_next):
        request_id = next(self._counter)
        response = await call_next(request_data)
        response["headers"] = response.get("headers", []) + [
            ("x-request-num", str(request_id)),
        ]
        return response


app.add_middleware(TimingMiddleware)
app.add_middleware(RequestCounterMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"])


@app.get("/")
async def index():
    return {"message": "middleware chain ran"}


@app.get("/slow")
async def slow():
    time.sleep(0.1)
    return {"message": "slept 100ms"}


if __name__ == "__main__":
    app.run(port=8000)
