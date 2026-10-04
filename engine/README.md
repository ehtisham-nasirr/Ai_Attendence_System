# FaceTrack recognition engine (CPU only)

Turns camera streams into recognition events. It **never decides attendance** — the backend does.
Requirements: §9, §10.1, §10.4, FR-14..FR-19, NFR-1..NFR-5, NFR-15. Rules: `Guardrails/standards/17-recognition-engine-cpu.md`.

```
                 ┌────────────────────────── engine node (one per server) ──────────────────────────┐
 camera RTSP ──► │ camera process (1 per camera)                       inference pool (N processes)  │
                 │  PyAV decoder ─► 1-slot latest-frame buffer          fixed threads, pinned cores   │
                 │  motion gate (320 px, ROI) ─► mode machine            ┌─ HIGH lane: entrance, /embed│
                 │  ROI crop ─► DETECT ─────────────────────────────────►│  LOW lane: general cameras  │
                 │  ByteTrack ─► quality gate ─► best 3 crops            │  YuNet / SFace|ArcFace /    │
                 │  EMBED(best 3) ─► vote 2-of-3 ─► LIVENESS ──────────►│  MiniFASNet + FAISS gallery │
                 │  emit + lock ─► publisher thread ─► storage + Redis   └─────────────────────────────┘
                 │                     └─► encrypted disk buffer (Redis/storage down)                 │
                 │ main process: FastAPI (internal API), supervisor, load monitor + degradation ladder│
                 └────────────────────────────────────────────────────────────────────────────────────┘
```

## How it keeps the feed smooth on CPU

| Mechanism | Where |
|---|---|
| Camera modes IDLE / ACTIVE / COOLDOWN / PAUSED | `app/scheduler/modes.py` |
| Keyframe-only decode while idle (non-key packets dropped before decoding) | `app/capture/decoder.py` |
| Latest frame only (1-slot overwrite buffer, never a queue) | `app/capture/frame_buffer.py` |
| Sub-stream when idle / for general cameras, main stream when an entrance camera is ACTIVE | `app/pipeline/camera_worker.py` |
| Detection on the ROI crop only, at the planned rate | `app/pipeline/camera_worker.py`, `app/scheduler/rates.py` |
| Best 3 crops per track embedded, track locked once decided | `app/pipeline/best_crops.py`, `app/pipeline/track_manager.py` |
| Bounded HIGH/LOW lanes, micro-batches ≤ 8 crops / ≤ 50 ms | `app/scheduler/inference_pool.py` |
| Degradation ladder (5 steps), sampled every 5 s | `app/scheduler/ladder.py`, `app/scheduler/supervisor.py` |
| Watchdogs: decoder (no frame 10 s), camera process (dead/hung), worker (dead/over memory) | `camera_worker.py`, `supervisor.py`, `inference_pool.py` |

Overflow policies are explicit: a full request lane rejects the request (the frame is skipped, the
embedding retried later); a full reply queue drops the reply (the request times out); a full disk
buffer refuses the event and logs `CRITICAL` (metric `facetrack_engine_lost_events`, must stay 0).

## Recognition decision (NFR-2: a false accept is worse than a miss)

A crop votes for employee X only if `score ≥ threshold` and `score − second-best ≥ margin`. A track
is confirmed only when ≥ 2 of its 3 embedded crops vote for X **and** no crop scores any other
employee at or above the threshold. Liveness (entrance cameras, when enabled) runs once on the best
crop; a spoof becomes an Unknown event. Thresholds come from the `settings` table / camera row and
are never lowered in code.

## Setup

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), PostgreSQL 16, Redis 7.

```bash
cd engine
uv sync                                   # CPU-only deps (onnxruntime, openvino, faiss-cpu, PyAV)
uv run python scripts/download_models.py  # YuNet + SFace, SHA-256 pinned; never committed
cp .env.example .env                      # fill in secrets; see app/config.py for every key
uv run uvicorn app.main:create_app --factory --port 8100
```

The engine reads cameras (`cameras.engine_node == ENGINE_NODE_NAME`), the gallery and settings from
PostgreSQL (read-only) and publishes to the Redis stream `recognition.events`. Snapshots are written
encrypted to object storage (`ENGINE_STORAGE_BACKEND=local` volume shared with the backend, or `s3`; see
`docs/adr/0005-object-storage-backend.md`).

### Running against a sample video (development)

Never use live production cameras in development. Generate a synthetic clip and point a camera at it:

```bash
uv run python scripts/sample_video.py recordings/sample.mp4 --seconds 60   # no faces, no people
# set ENGINE_ALLOW_FILE_SOURCES=true and create a camera with URL file:///abs/path/recordings/sample.mp4
```

To run the engine in Docker together with the backend stack on one laptop or test machine, use the
overlay `infra/docker-compose.dev.yml` (`make dev`, or the plain `docker compose` commands in
`docs/local-development.md`). Copy clips into the engine's `videos` volume
(`docker compose cp data/videos/. engine:/srv/videos`) and use the camera URL
`file:///srv/videos/<clip>.mp4` on engine node `node-1`. Live view is not available for file sources,
because MediaMTX cannot pull `file://` URLs.

### Models

| Role | Default | Alternative | Notes |
|---|---|---|---|
| Detector | YuNet 2023mar (MIT) | — | post-processing verified against OpenCV `FaceDetectorYN` |
| Embedder | SFace 2021dec (Apache-2.0), 128-d | ArcFace R50 (`arcface_r50`), 512-d | ArcFace weights need an InsightFace commercial licence |
| Liveness | MiniFASNet (Apache-2.0) | — | convert official weights to ONNX; not shipped |

OpenVINO on AVX-512-bf16/AMX Xeons defaults to bf16, which shifts landmarks and embeddings; the
engine forces `f32` (`ENGINE_OPENVINO_PRECISION`). INT8: `uv sync --group tools` then
`scripts/convert_int8.py`; a converted model must pass `scripts/evaluate.py` before use.

### Adding an engine node

Run `infra/docker-compose.engine.yml` on the new server with a new `ENGINE_NODE_NAME`, then assign
cameras to it in the Cameras screen (`engine_node`). Nodes share PostgreSQL, Redis and storage.

## Internal API (§12.2) — backend network only, header `X-Engine-Token`

`POST /embed` · `POST /gallery/reload` · `POST /cameras/sync` · `GET /cameras/status` ·
`POST /cameras/test` · `GET /load` · `GET /health` (no token) · `GET /metrics` (no token).
Responses use the standard envelope `{success, message, data}`. The backend also triggers reloads
through Redis channel `facetrack.engine.control` (`{"type": "gallery_reload" | "cameras_sync"}`).

## Tests, lint, types, measurement

```bash
uv run pytest                                   # unit + pipeline tests (synthetic data only)
TEST_DATABASE_URL=postgresql+asyncpg://... uv run pytest tests/test_db_loaders.py
uv run ruff check . && uv run ruff format --check . && uv run mypy app
uv run python scripts/benchmark_cpu.py --runtime openvino   # per-step ms, CPU % per camera
uv run python scripts/evaluate.py /data/eval --threshold 0.36 --margin 0.08   # TAR/FAR, consented data only
```

Every pipeline/model/scheduling change follows `Guardrails/commands/engine-change.md` (benchmark
before/after, evaluation, 30-minute soak) and records the numbers in `batch/`.

## Troubleshooting

| Symptom | Check |
|---|---|
| Camera never leaves IDLE | ROI too small / wrong; `engine.motion_min_area_ratio`; camera GOP > 1 s |
| Camera shows `connected=false` | `/cameras/status.last_error` (URLs are redacted); network to the camera; backoff caps at 60 s |
| Camera refused at sync | `/cameras/status.last_error`: no threshold for the embedder model, or liveness enabled without a model |
| Stuck at a degraded ladder level | `/load`: CPU above `engine.ladder_cpu_low_pct` or lag above `engine.ladder_lag_high_s`; add a node |
| Events not reaching the backend | `facetrack_engine_buffered_events` > 0 means Redis/storage is down; they replay automatically |
| Nobody recognised | gallery empty for this embedder model (`/health.gallery_version`, `facetrack_engine_gallery_embeddings`) |
