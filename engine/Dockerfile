# FaceTrack recognition engine — CPU only (no CUDA/GPU packages). Build context: repository root.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /srv
COPY common/ common/
COPY engine/pyproject.toml engine/uv.lock engine/README.md engine/
WORKDIR /srv/engine
RUN uv sync --frozen --no-dev --no-install-project

COPY engine/app app
COPY engine/scripts scripts
RUN uv sync --frozen --no-dev

# Models are fetched at build time with pinned SHA-256 (never committed to Git).
RUN uv run --no-sync python scripts/download_models.py --dest /srv/engine/models

RUN useradd --system --uid 10001 facetrack && mkdir -p /srv/engine/buffer && chown facetrack /srv/engine/buffer
USER facetrack

EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://localhost:8100/health || exit 1
CMD ["/srv/engine/.venv/bin/uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100", "--workers", "1"]
