# The detector test bench: dashboard, queue and GitHub watch in one container.
# Build from the repo root:  docker build -f apps/sim-host/bench.Dockerfile -t dog-bench .
# Run:  docker run -p 8000:8000 -v bench-data:/data dog-bench
# Deploying on Coolify: docs/simulator/bench.md
FROM python:3.12-slim

# osmesa: MuJoCo renders on the CPU, no screen or GPU. libgl/glib: OpenCV in Ultralytics.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libosmesa6 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

ENV MUJOCO_GL=osmesa \
    PYOPENGL_PLATFORM=osmesa \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    BENCH_DATA=/data \
    PORT=8000

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/dog-protocol packages/dog-protocol
COPY apps/sim-host apps/sim-host
RUN uv sync --locked --no-dev --package dog-sim-host --extra bench

VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s \
    CMD ["/app/.venv/bin/python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/')"]
CMD ["/app/.venv/bin/python", "-m", "dog_sim_host.bench", "serve"]
