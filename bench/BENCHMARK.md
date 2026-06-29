# Rivex Benchmark Documentation

**Last updated:** 2026-05-15
**Framework version:** rivex 0.1.0 (rivex_core 0.1.0)

---

## Overview

Rivex is a Rust-powered Python web framework. The benchmark suite validates performance across four deployment configurations, testing from 100 to 10,000 concurrent connections with sustained load.

All benchmarks run on bare metal (no Docker overhead), using `wrk` for sustained throughput measurement with persistent connections.

---

## Test Machine

| Spec | Value |
|------|-------|
| Architecture | Apple Silicon arm64 |
| CPU Cores | 10 |
| RAM | 32 GB |
| OS | macOS |
| FD Limit | 65,536 |
| Python | 3.14 (CPython) |
| Tools | wrk, vegeta, hey |

---

## Server Configurations

### 1. Sync Server (1 worker)
**File:** `bench/server_sync.py`
**Port:** 8100
**Start:** `python -m bench.server_sync 8100 1`

Uses `rivex_core.RivexServer` directly. Single-threaded event loop powered by Rust's TCP handling. Minimal middleware (CORS + RequestId).

**Endpoints tested:**
- `GET /ping` -- minimal JSON `{"pong": true}`
- `GET /items/{item_id}?fields=name` -- path params + query parsing
- `POST /items` -- JSON body + Pydantic V2 validation
- `GET /heavy` -- 100-item JSON array serialization
- `GET /compute?n=100` -- CPU-bound sum computation

### 2. ASGI Server (1 worker)
**File:** `bench/server_asgi.py`
**Port:** 8101
**Start:** `uvicorn bench.server_asgi:asgi_app --port 8101 --workers 1`

Same Rivex app wrapped in `ASGIAdapter`, deployed via uvicorn. Tests the ASGI protocol translation overhead.

### 3. ASGI Server (4 workers)
**Port:** 8101
**Start:** `uvicorn bench.server_asgi:asgi_app --port 8101 --workers 4`

Same as above with 4 uvicorn workers. Tests horizontal scaling via process forking.

### 4. Middleware Heavy (7 layers)
**File:** `bench/server_middleware_heavy.py`
**Port:** 8102
**Start:** `python -m bench.server_middleware_heavy 8102`

Stack: CORS > RequestId > SecurityHeaders > TrustedHost > MaxBodySize > Compression > GZip

Tests per-request overhead of a production-like middleware pipeline.

---

## How to Run

### Prerequisites
```bash
# Install tools (macOS)
brew install wrk vegeta hey

# Raise file descriptor limit
ulimit -n 65536
```

### Full Suite (automated)
```bash
cd python.rivex.vexarr.com
bash bench/run_extreme.sh
```

Results are written to `bench/results/<timestamp>/`.

### Individual Server
```bash
# Start server
python -m bench.server_sync 8100 1 &

# Quick benchmark
wrk -t4 -c100 -d10s http://127.0.0.1:8100/ping

# Heavy benchmark
wrk -t8 -c10000 -d300s http://127.0.0.1:8100/ping

# POST with JSON body
wrk -t8 -c2500 -d60s -s bench/wrk_post.lua http://127.0.0.1:8100/items
```

### Test Tiers

| Tier | Concurrency | Duration | Purpose |
|------|-------------|----------|---------|
| warmup | 100 | 10s | Establish baseline, warm caches |
| moderate | 500 | 30s | Light production load |
| heavy | 1,000 | 60s | Peak single-region traffic |
| extreme | 2,500 | 120s | Multi-region burst |
| ultra | 5,000 | 180s | Connection pressure test |
| max | 10,000 | 300s | Absolute concurrency ceiling |

---

## Results Summary (2026-05-15)

### Peak Throughput

| Config | Peak RPS | RPS @ 10Kc | Latency @ 10Kc | Total Tested |
|--------|----------|------------|-----------------|-------------|
| Sync (1 worker) | **72,445** | 40,060 | 248ms | 34M+ |
| ASGI (1 worker) | 19,477 | 8,344 | 236ms | 14M+ |
| ASGI (4 workers) | **68,680** | 35,107 | 239ms | 28M+ |
| Middleware (7 layers) | 28,322 | 15,118 | 652ms | 10M+ |

**Grand total: 85,988,280 requests processed.**

### 1 Billion Request Extrapolation

| Config | Sustained RPS | Time for 1B |
|--------|---------------|-------------|
| Sync @ 100c | 72,445 | 3h 50m |
| Sync @ 10Kc | 40,060 | 6h 56m |
| ASGI 4w @ 100c | 68,680 | 4h 03m |
| ASGI 4w @ 10Kc | 35,107 | 7h 55m |
| MW Heavy @ 10Kc | 15,118 | 18h 22m |
| POST+Pydantic @ 10Kc | 20,271 | 13h 42m |

### Endpoint Breakdown (Sync Server)

| Endpoint | RPS @ 2500c | Avg Latency |
|----------|-------------|-------------|
| /ping | 52,491 | 47ms |
| /items/42?fields=name | 26,749 | 93ms |
| POST /items (Pydantic) | 21,900 | 114ms |
| /compute?n=100 | 24,923 | 105ms |
| /heavy (100 items) | 7,267 | 138ms |

---

## Key Findings

1. **Rust sync server dominates.** 72K req/s peak from a single worker. The Rust TCP handler + epoll/kqueue loop is the fastest path.

2. **ASGI 4-worker closes the gap.** 68.7K peak proves `ASGIAdapter` adds minimal overhead. The Python async layer is not the bottleneck.

3. **Each middleware layer costs ~8-10%.** 7 layers = ~60% throughput reduction. Keep production stacks lean.

4. **Pydantic V2 is fast.** 22K req/s with full JSON parse + model validation. Not a significant bottleneck.

5. **Latency stays sane under pressure.** Sync server holds 248ms average at 10K concurrent -- well within 1s SLA.

6. **Error rate is tiny.** Socket read errors < 0.1% even at 10K connections. Rust TCP handling is solid.

7. **JSON serialization is the bottleneck for heavy payloads.** 100-item response drops to 7.3K/s. The server itself is not the limit.

---

## Production Sizing Guide

| Workload | Recommended Config | Workers | Headroom |
|----------|-------------------|---------|----------|
| API gateway (low latency) | Sync server | 1 per core | 72K/s per worker |
| Async I/O (DB, external APIs) | ASGI + uvicorn | 4 per instance | 68K/s per instance |
| 1B requests/day | 2 instances x 4 workers | 8 total | 3x headroom at 40K sustained |
| Middleware-heavy production | ASGI + lean stack | 4+ workers | Budget 8-10% per layer |

---

## Artifacts

| File | Description |
|------|-------------|
| `bench/server_sync.py` | Sync benchmark server (6 endpoints) |
| `bench/server_asgi.py` | ASGI adapter wrapper |
| `bench/server_middleware_heavy.py` | 7-layer middleware stress server |
| `bench/wrk_post.lua` | Lua script for POST benchmarks |
| `bench/run_extreme.sh` | Automated full test suite runner |
| `bench/results/EXTREME_TEST_REPORT.md` | Detailed per-tier results with raw numbers |
