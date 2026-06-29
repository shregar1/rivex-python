"""Server with full middleware stack for stress testing the pipeline."""

from rivex import Rivex
from rivex.middleware import (
    CompressionMiddleware,
    CORSMiddleware,
    GZipMiddleware,
    MaxBodySizeMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    TrustedHostMiddleware,
)

app = Rivex(title="Middleware Stress", version="1.0.0", docs_url=None, redoc_url=None)

# Heavy middleware stack — 7 layers
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
app.add_middleware(MaxBodySizeMiddleware, max_size=10_485_760)
app.add_middleware(CompressionMiddleware, minimum_size=500)
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.get("/ping")
async def ping():
    return {"pong": True}


@app.get("/heavy")
async def heavy():
    return {"data": [{"id": i, "value": f"row-{i}" * 10} for i in range(200)]}


@app.post("/echo")
async def echo(body: dict):
    return body


if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8102
    app.run(host="0.0.0.0", port=port)
