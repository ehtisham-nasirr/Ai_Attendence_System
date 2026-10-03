# FaceTrack backend: API, Celery worker and Celery beat share this image. Build context: repository root.
# Pango/HarfBuzz are WeasyPrint (PDF reports) system libraries.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /srv
COPY common/ common/
COPY backend/pyproject.toml backend/uv.lock backend/README.md backend/
WORKDIR /srv/backend
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app app
COPY backend/alembic alembic
COPY backend/alembic.ini alembic.ini
COPY backend/gunicorn.conf.py gunicorn.conf.py
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 facetrack && mkdir -p /srv/media && chown facetrack /srv/media
USER facetrack
ENV PATH="/srv/backend/.venv/bin:$PATH"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://localhost:8000/health || exit 1
# Worker:  celery -A app.worker worker --loglevel=INFO --concurrency=4
# Beat:    celery -A app.worker beat --loglevel=INFO --schedule /tmp/celerybeat-schedule
# Migrate: alembic upgrade head
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app.main:create_app()"]
