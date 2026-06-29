# rivex-admin

A sleek, React-based admin dashboard plugin for the [Rivex](https://github.com/vexarr/rivex) web framework.

## Features

- Fully bundled React SPA dashboard
- Real-time logs viewer
- Configuration editor
- Codegen resource scaffolder integration
- Live protocol monitoring dashboard (HTTP, WebSocket, WebRTC, gRPC) with per-route metrics, EWMA latency quantiles, and adapter health

## Installation

The monitoring dashboard also requires the `rivex_monitor` package, included automatically with `rivex[admin]`, or install separately:

```bash
pip install rivex-monitor
```

Normally installed as part of rivex extras:

```bash
pip install rivex[admin]
```
