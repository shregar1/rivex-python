# Configuration & Deployment

This page covers configuration, running the server, scaling with workers, the CLI, and packaging Rivex for production.

## Configuration with Settings

`Settings` loads typed configuration from environment variables (and an optional `.env` file). It's a `Schema` subclass, so fields are validated and coerced.

```python
from rivex import Settings


class AppSettings(Settings):
    database_url: str
    secret_key: str
    debug: bool = False
    port: int = 8000

    model_config = {"env_prefix": "MYAPP_", "env_file": ".env"}


settings = AppSettings.from_env()
```

With `env_prefix="MYAPP_"`, the `database_url` field reads `MYAPP_DATABASE_URL`. Real environment variables take precedence over `.env`. Use `Settings.from_dict({...})` to build config directly in tests.

```bash
# .env
MYAPP_DATABASE_URL=postgres://localhost/app
MYAPP_SECRET_KEY=change-me
MYAPP_DEBUG=false
```

## Running the server

Run programmatically:

```python
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, workers=1)
```

`run(host="127.0.0.1", port=8000, workers=1)` blocks, serving requests and handling `SIGINT`/`SIGTERM` for graceful shutdown.

## The `rivex` CLI

The package installs a `rivex` command:

| Command | Purpose |
| --- | --- |
| `rivex run main:app` | Run the server (`--host`, `--port`, `--workers`, `--reload`) |
| `rivex routes main:app` | Print every registered route |
| `rivex version` | Show the installed version |

```bash
# Development: live reload on file changes
rivex run main:app --reload

# Production-ish: four workers on all interfaces
rivex run main:app --host 0.0.0.0 --port 8000 --workers 4
```

The app import path is `module:variable` — `main:app` means "the `app` object in `main.py`".

## Scaling with workers

`--workers N` (or `workers=N`) spawns multiple OS workers that share the listening port via the kernel's `SO_REUSEPORT`. The kernel load-balances connections across them — no external process manager required for basic scaling.

> **Operational gotcha.** Because workers bind with `SO_REUSEPORT`, several independent server processes on the same port will *silently share* it and round-robin requests. If you restart during development without stopping the old process, stale workers can keep answering and produce confusing, intermittent responses. Always stop the previous server cleanly — e.g. `lsof -ti:8000 | xargs kill -9` — before starting a new one.

## Containerizing

A minimal production image:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000
CMD ["rivex", "run", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

```text
# requirements.txt
rivex>=0.1.0
# ...your application dependencies
```

Because `rivex-core` ships as a prebuilt wheel, no Rust toolchain is needed in the build.

## A production checklist

- **Config**: load secrets via `Settings`/env, never hard-code them; set `debug=False`.
- **TLS**: terminate HTTPS at a proxy and add `HTTPSRedirectMiddleware` + `SecurityHeadersMiddleware`.
- **Limits**: add `MaxBodySizeMiddleware`, `TimeoutMiddleware`, and rate limiting/throttling.
- **Hosts**: restrict with `TrustedHostMiddleware`.
- **Observability**: wire metrics, tracing, structured logs, and `HealthCheck` probes (see *Observability*).
- **Blocking work**: wrap synchronous drivers in `run_in_threadpool` (see *Background Tasks & Concurrency*).
- **Workers**: size `--workers` to your CPU and stop old processes cleanly between deploys.

## Next

The **API Reference** is a one-page import cheat sheet for everything covered here.
