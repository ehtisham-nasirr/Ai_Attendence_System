# FaceTrack monorepo tasks (standards/01). Each Python package has its own uv environment.
.PHONY: help sync test lint typecheck test-common test-engine test-backend lint-common lint-engine lint-backend models sample-video benchmark migrate gen-api seed

help:
	@grep -E '^[a-z-]+:' Makefile | sed 's/:.*//' | sort | tr '\n' ' '; echo

sync:
	cd common && uv sync --all-extras
	cd engine && uv sync
	cd backend && uv sync

models:
	cd engine && uv run python scripts/download_models.py --dest models

sample-video:
	cd engine && uv run python scripts/sample_video.py recordings/sample.mp4 --seconds 60

benchmark:
	cd engine && uv run python scripts/benchmark_cpu.py --runtime openvino

test: test-common test-engine test-backend

test-common:
	cd common && uv run pytest -q

test-engine:
	cd engine && uv run pytest -q

# Uses TEST_DATABASE_URL / TEST_REDIS_URL when set, otherwise testcontainers (Docker).
test-backend:
	cd backend && uv run pytest -q

lint: lint-common lint-engine lint-backend

lint-common:
	cd common && uv run ruff check . && uv run ruff format --check .

lint-engine:
	cd engine && uv run ruff check . && uv run ruff format --check .

lint-backend:
	cd backend && uv run ruff check . && uv run ruff format --check .

typecheck:
	cd common && uv run mypy facetrack_common
	cd engine && uv run mypy app
	cd backend && uv run mypy app

migrate:
	cd backend && uv run alembic upgrade head

seed:
	cd backend && uv run python -m app.scripts.seed

# OpenAPI spec for the portal client (frontend: npm run gen-api).
gen-api:
	cd backend && uv run python -m app.scripts.export_openapi
