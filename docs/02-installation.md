# Installation

Rivex is distributed on PyPI as the `rivex` package. It requires **Python 3.10 or newer**.

## Install

```bash
pip install rivex
```

This pulls in the framework along with its core dependencies:

- **`rivex-core`** — the compiled Rust extension (the HTTP server, JSON encoder, hashing, JWT, and validators). Prebuilt wheels are published for common platforms, so no Rust toolchain is needed to install.
- **`pydantic>=2.0`** — used for model validation and interoperable with Rivex's own `Schema`.
- **`orjson>=3.9`** — fast JSON serialization.

## Optional extras

Some capabilities pull in extra packages. Install them with extras syntax:

```bash
# Schemax IDL toolchain (`rivex.schemax` shim + `rivex schemax …` CLI)
pip install "rivex[schemax]"

# Development tooling: pytest, httpx, mypy, ruff, schemax
pip install "rivex[dev]"
```

A few features integrate with libraries you install yourself when you need them:

| Feature | Extra dependency |
| --- | --- |
| HTML templates (`Jinja2Templates`) | `jinja2` |
| OpenTelemetry tracing export (`OTelSpanExporter`) | `opentelemetry-sdk` |
| Schemax IDL | `schemax` (or the `schemax` extra) |

If an optional dependency is missing, Rivex degrades gracefully — for example, tracing falls back to a console exporter when OpenTelemetry isn't installed.

## Verify the install

```bash
rivex version
```

You should see something like `Rivex 0.1.0`. The `rivex` command-line tool is installed alongside the package; see *Configuration & Deployment* for everything it can do.

## A minimal project layout

Rivex has no required project structure. A single file is enough to start:

```
myapi/
├── main.py          # your Rivex app
├── requirements.txt # rivex, plus your own deps
└── .env             # optional, read by Settings
```

```python
# main.py
from rivex import Rivex

app = Rivex()


@app.get("/health")
async def health():
    return {"status": "ok"}
```

Run it during development with autoreload:

```bash
rivex run main:app --reload
```

You're ready to build — head to the **Quickstart**.
