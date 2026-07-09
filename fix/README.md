This directory documents issues found in the rivex Python SDK (v0.1.0). Each file covers a specific area.

| # | File | Severity | One-line |
|---|---|---|---|
| 01 | `01-asgi-lifespan.md` | HIGH | ASGI lifespan fails on startup errors |
| 02 | `02-sse-handler-await.md` | HIGH | SSE handler doesn't await async generators |
| 03 | `03-multiworker-uvicorn.md` | HIGH | Multi-worker uvicorn uses wrong module |
| 04 | `04-body-validation.md` | HIGH | Required body field validation silently skipped |
| 05 | `05-websocket-constructor.md` | HIGH | WebSocket constructor signature mismatch |
| 06 | `06-cli-code-injection.md` | HIGH | CLI dev reload has code injection |
| 07 | `07-worker-entry-race.md` | HIGH | Worker entry uses type before module-level assignment |
| 08 | `08-medium-issues.md` | MEDIUM | 11 medium-severity issues (RST, CORS, duplicates) |
| 09 | `09-low-issues.md` | LOW | 16 low-severity issues (naming, docstrings, etc.) |
| 10 | `10-stub-syntax-error.md` | HIGH | `rivex_core/__init__.pyi` line 334 has unclosed paren — breaks mypy |
| 11 | `11-app-py-shadowing.md` | HIGH | `app.py` from third-party editable installs shadows user's `app/` package |
| 12 | `12-streaming-render-body-bug.md` | MEDIUM | `StreamingResponse._render_body()` is broken in async contexts (no-core path) |
| 13 | `13-asyncio-run-in-loop.md` | HIGH | Multiple `asyncio.run` / `loop.run_until_complete` from inside running loop |
| 14 | `14-asgi-dead-code.md` | LOW | Dead `len(self._handlers)` no-op in `ASGIAdapter._build()` |
| 15 | `15-cors-origin-bypass.md` | MEDIUM | CORS allows arbitrary origin when not in allow list |
| 16 | `16-body-json-error.md` | LOW | `Request.body_json()` raises bare `JSONDecodeError` without request context |
| 17 | `17-multipart-file-scalar-binding.md` | HIGH | Scalar sibling of `File()` silently bound to query-only, never multipart body; `Form()`-DTO validation chokes on `extra="forbid"` |

**Totals:** 12 HIGH, 3 MEDIUM, 2 LOW = 17 issues documented.
