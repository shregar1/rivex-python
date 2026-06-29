"""Sync server for extreme load testing — exercises ALL rivex features."""

from pydantic import BaseModel

from rivex import Header, Path, Query, Rivex
from rivex.middleware import (
    CORSMiddleware,
    RequestIdMiddleware,
)

app = Rivex(title="Extreme Bench", version="1.0.0", docs_url=None, redoc_url=None)

app.add_middleware(CORSMiddleware, allow_origins=["*"])
app.add_middleware(RequestIdMiddleware)


class Item(BaseModel):
    id: int
    name: str
    price: float


# ── 1. Baseline: minimal JSON ──
@app.get("/ping")
async def ping():
    return {"pong": True}


# ── 2. Path + query params ──
@app.get("/items/{item_id}")
async def get_item(item_id: int = Path(...), fields: str = Query("all")):
    return {"id": item_id, "fields": fields}


# ── 3. POST with JSON body + Pydantic ──
@app.post("/items", status_code=201, response_model=Item)
async def create_item(item: Item):
    return item


# ── 4. Headers injection ──
@app.get("/echo-agent")
async def echo_agent(user_agent: str = Header("user-agent")):
    return {"agent": user_agent}


# ── 5. Heavy JSON payload ──
@app.get("/heavy")
async def heavy():
    return {"data": [{"id": i, "value": f"item-{i}"} for i in range(100)]}


# ── 6. Compute-bound endpoint ──
@app.get("/compute")
async def compute(n: int = Query(1000)):
    total = sum(range(n))
    return {"sum": total}


if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8100
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    app.run(host="0.0.0.0", port=port, workers=workers)
