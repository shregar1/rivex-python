"""ASGI server app for extreme load testing — same endpoints, uvicorn-deployed."""

from bench.server_sync import app  # reuse the same Rivex app
from rivex.asgi import ASGIAdapter

asgi_app = ASGIAdapter(app)
