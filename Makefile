# FaceTrack monorepo tasks (standards/01). Each Python package has its own uv environment.
.PHONY: help sync test lint typecheck test-common test-engine test-backend test-frontend lint-common lint-engine lint-backend lint-frontend build-frontend e2e models sample-video benchmark migrate gen-api seed

help:
	@grep -E '^[a-z-]+:' Makefile | sed 's/:.*//' | sort | tr '\n' ' '; echo

sync:
	cd common && uv sync --all-extras
	cd engine && uv sync
	cd backend && uv sync
	cd frontend && npm ci

models:
	cd engine && uv run python scripts/download_models.py --dest models

sample-video:
	cd engine && uv run python scripts/sample_video.py recordings/sample.mp4 --seconds 60

benchmark:
	cd engine && uv run python scripts/benchmark_cpu.py --runtime openvino

test: test-common test-engine test-backend test-frontend

test-common:
	cd common && uv run pytest -q

test-engine:
	cd engine && uv run pytest -q

# Uses TEST_DATABASE_URL / TEST_REDIS_URL when set, otherwise testcontainers (Docker).
test-backend:
	cd backend && uv run pytest -q

test-frontend:
	cd frontend && npm test

# Needs a running backend and E2E_USERNAME / E2E_PASSWORD of a non-production Super Admin.
e2e:
	cd frontend && npm run build && npm run e2e

lint: lint-common lint-engine lint-backend lint-frontend

lint-common:
	cd common && uv run ruff check . && uv run ruff format --check .

lint-engine:
	cd engine && uv run ruff check . && uv run ruff format --check .

lint-backend:
	cd backend && uv run ruff check . && uv run ruff format --check .

lint-frontend:
	cd frontend && npm run lint

build-frontend:
	cd frontend && npm run build

typecheck:
	cd common && uv run mypy facetrack_common
	cd engine && uv run mypy app
	cd backend && uv run mypy app
	cd frontend && npm run typecheck

migrate:
	cd backend && uv run alembic upgrade head

seed:
	cd backend && uv run python -m app.scripts.seed

# OpenAPI spec (docs/openapi.yaml) and the generated portal client (standards/08).
gen-api:
	cd backend && uv run python -m app.scripts.export_openapi
	cd frontend && npm run gen-api
