# =============================================================================
# Rivex — Multi-stage Docker image
#
# Variants (use --build-arg VARIANT=...):
#   alpine      Python 3.13-slim on Alpine  (default, ~120 MB)
#   distroless  gcr.io/distroless/python3   (~80 MB, no shell, no package manager)
#   full        python:3.13-slim-bookworm   (~160 MB, build tools included)
#
# Example:
#   docker build --build-arg VARIANT=alpine -t rivex-app .
#   docker run -p 8000:8000 rivex-app
# =============================================================================

ARG VARIANT=alpine

# ── Stage 1: Build ───────────────────────────────────────────────────────────
FROM python:3.13-alpine AS build-alpine
FROM python:3.13-slim-bookworm AS build-full
FROM python:3.13-slim-bookworm AS build-distroless

FROM build-${VARIANT} AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl pkg-config && \
    rm -rf /var/lib/apt/lists/*

# Install Rust (needed for maturin)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /build

# Install maturin
RUN pip install --no-cache-dir maturin

# Copy only build files first for layer caching
COPY Cargo.toml Cargo.lock pyproject.toml maturin.toml README.md ./
COPY crates/ ./crates/
COPY src/ ./src/

# Build the wheel
RUN maturin build --release --out /build/dist

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.13-alpine AS runtime-alpine
FROM python:3.13-slim-bookworm AS runtime-full
FROM gcr.io/distroless/python3 AS runtime-distroless

FROM runtime-${VARIANT} AS final

WORKDIR /app

# Install the built wheel + minimal deps
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Copy application code (override with mount or COPY in your own Dockerfile)
COPY . /app

# Default port
ENV RIVEX_HOST=0.0.0.0
ENV RIVEX_PORT=8000

EXPOSE ${RIVEX_PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${RIVEX_PORT}/healthz')" || exit 1

# Non-root user for security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

ENTRYPOINT ["python3", "-m", "rivex", "run", "main:app"]
