# Batch: build-cpu-recognition-engine

**Date:** 2026-10-04 00:55
**Type:** engine-change
**Command Used:** commands/engine-change.md (first build of the engine; there is no earlier baseline)
**Standards Referenced:** standards/01-project-structure.md, standards/09-forms-errors-logging.md, standards/10-python-standards.md, standards/11-testing.md, standards/12-git-standards.md, standards/13-documentation-and-comments.md, standards/17-recognition-engine-cpu.md, standards/18-privacy-and-biometric-data.md
**Requirements:** FR-2, FR-4, FR-5, FR-9, FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, NFR-2, NFR-5, NFR-7, NFR-8, NFR-13, NFR-15 (NFR-1, NFR-3, NFR-4 not verifiable here — see Testing)

## Summary
Built the CPU-only recognition engine (requirements §9, §10.1, §10.4, §16 Phases 1–2) and the shared `common/` package it depends on: the event contract, constants, AES-256-GCM helper, settings registry, SQLAlchemy models for all 16 tables, engine API schemas and object storage.

## Changes Made
- `common/`: `events.py` (§10.2 contract plus additive `model_name`, `engine_node`, `embedding_encrypted` and `bbox`, Q8); `constants.py`; `crypto.py` (AES-256-GCM, purpose-bound); `settings_keys.py` (every tunable and its default, validated); `models/` (16 tables, with `recognition_events` partitioned by month and embeddings as ciphertext per ADR-0001); `schemas/` (envelope and engine API); `jsonlog.py`; `storage.py` (local/S3 object store, ADR-0005).
- Engine models: `Detector`, `Embedder` and `LivenessChecker` interfaces. YuNet on OpenVINO/ONNX Runtime with its own post-processing, which matches OpenCV `FaceDetectorYN` exactly. SFace (default) and ArcFace R50 embedders, a MiniFASNet liveness checker, and 5-point Umeyama alignment matching OpenCV `alignCrop` (max pixel difference 1).
- Capture: PyAV decoder thread. It drops non-key packets in IDLE/COOLDOWN and resumes full decoding cleanly from the next keyframe. It uses a 1-slot latest-frame buffer, reconnect backoff from 2 s to 60 s, real-time pacing for dev clips, and URL-free error text. There is also a snapshot grabber for FR-2.
- Scheduler: camera mode state machine, 5-step degradation ladder, rate plans (role × mode × level × peak windows), operating hours, and a bounded HIGH/LOW inference pool. The pool uses ≤ 8-crop / ≤ 50 ms micro-batches, a fixed per-worker thread budget with optional core pinning, and restarts dead or over-memory workers. The supervisor handles camera process lifecycle, two-level watchdogs, the load monitor, gallery hot reload and the Redis control channel.
- Pipeline: motion gate (320 px, ROI-masked), ROI crop/filter, quality gate (size, sharpness, pose, detector score), ByteTrack tracking, best-3-crop selection, strict voting (threshold + margin, 2 of 3, and no other employee may score at or above threshold), and liveness once per confirmed track. The track manager emits one event per track and locks it, and turns short or ambiguous tracks into Unknown. A per-camera worker process ties these together.
- Publisher: encrypted snapshot to object storage, then XADD to `recognition.events`. Each event gets a sequence number when emitted, and an encrypted, bounded disk buffer replays events in order after an outage.
- Internal API: `/embed`, `/gallery/reload`, `/cameras/sync`, `/cameras/status`, `/cameras/test`, `/load`, `/health`, `/metrics`, with a token header and the standard envelope.
- Scripts: `download_models.py` (SHA-256 pinned), `evaluate.py` (TAR/FAR/ROC), `benchmark_cpu.py`, `convert_int8.py` (NNCF), `sample_video.py` (synthetic, face-free clips).
- CPU-only Dockerfile, `.env.example`, README, root `Makefile`; `.gitignore` corrected so the code packages named `models/` are tracked.

## Files Changed
```
common/pyproject.toml, common/uv.lock, common/README.md
common/facetrack_common/{__init__,constants,crypto,events,jsonlog,settings_keys,storage}.py
common/facetrack_common/models/{__init__,base,organization,employee,camera,recognition,attendance,auth,system}.py
common/facetrack_common/schemas/{__init__,envelope,engine}.py
common/tests/{test_crypto,test_events,test_settings_keys,test_models,test_jsonlog,test_storage}.py
engine/pyproject.toml, engine/uv.lock, engine/README.md, engine/.env.example, engine/Dockerfile
engine/app/{config,db,main,metrics}.py
engine/app/api/{deps,routes}.py
engine/app/capture/{decoder,frame_buffer,snapshot}.py
engine/app/models/{base,runtime,alignment,yunet,embedders,liveness,factory}.py
engine/app/pipeline/{roi,motion,quality,tracking,best_crops,voting,track_manager,enrollment,camera_worker}.py
engine/app/gallery/{index,loader}.py
engine/app/publisher/{disk_buffer,event_publisher}.py
engine/app/scheduler/{modes,ladder,rates,operating_hours,camera_config,inference_pool,supervisor}.py
engine/scripts/{download_models,evaluate,benchmark_cpu,convert_int8,sample_video}.py
engine/tests/*.py (16 files)
Makefile, .gitignore, docs/open-questions.md, docs/adr/0005-object-storage-backend.md
```

## Database Changes
None applied by the engine (it is read-only). The models are defined here; the Alembic migration is in the Phase 2 batch.

## CPU / Performance Impact
This is the first build, so there is no "before". Measured on the **dev container** (4 vCPU Intel Xeon @ 2.1 GHz with AVX-512/AMX, 15 GB RAM), **not** the reference server. Synthetic 1080p H.264 clip, 25 fps, GOP 25, no faces.

| Step (mean ms, 2 threads) | OpenVINO f32 | ONNX Runtime |
|---|---|---|
| Decode 1080p, full (per frame) | 1.81 | 2.08 |
| Decode 1080p, keyframe only (per keyframe) | 19.49 | 18.97 |
| BGR conversion 1080p | 0.47 | 0.63 |
| Motion gate (1080p → 320 px) | 2.18 | 2.40 |
| YuNet detection (640 input) | 7.17 | 7.51 |
| Alignment / quality | 0.07 / 0.24 | 0.09 / 0.23 |
| SFace embedding, 1 crop / 3 crops | 5.07 / 15.94 | 17.34 / 52.80 |
| FAISS match, 5,000 × 10 gallery, 128-d / 512-d | 0.71 / 2.67 | 0.64 / 2.55 |

- One camera: IDLE 3.6% of one core at 1.0 fps processed; ACTIVE (full decode + motion + detection at 4 FPS) 15.3% at 3.6 fps processed (OpenVINO).
- NFR-5 (≤ 10 ms per face for 5,000 employees): met on this machine (2.7 ms worst case, 512-d). There is also an automated test.
- **Soak** (commands/engine-change.md step 7): 4 cameras (ENTRY, ENTRY_EXIT, 2 × GENERAL) on a looped 1080p clip with periodic motion, 2 inference workers × 1 thread, OpenVINO, real PostgreSQL and Redis, for 30.5 minutes plus a 7.5-minute extension:
  - The ladder stayed at level 1, with 0 restarts, 0 ERROR/CRITICAL log lines and 0 camera errors.
  - Lag averaged 0.037 s (max 0.197 s). Average CPU was 10.6% (max 24.1%). There were 848 mode changes. The inference queues ended empty, and each worker completed about 5,750 tasks.
  - Total RSS of all 8 engine processes went 1916.9 → 1933.9 MB during the first 30 minutes (warm-up), then stayed flat at 1933.9 MB for the extra 7.5 minutes. Per-process RSS also showed 0.0 MB change over a 150 s window. No growing lag was seen.
- The figures printed by `benchmark_cpu.py` ("derived_not_measured": 73 cameras ACTIVE at once on 16 cores) are arithmetic only. They are **not meaningful**, because the synthetic clip decodes far more cheaply than real camera footage.

## Testing
- `common`: 45 tests pass; ruff, ruff format and mypy --strict are clean.
- `engine`: 111 tests pass (109 unit/pipeline + 2 against real PostgreSQL with `TEST_DATABASE_URL`); ruff, ruff format and mypy --strict (`app/`) are clean; coverage 80% overall. The decision logic sits at 94–100%: voting, ladder, modes, rates, track manager, motion, disk buffer, alignment and enrollment validation.
- Model equivalence on synthetic images, both runtimes: YuNet scores and landmarks match OpenCV exactly; SFace cosine vs OpenCV is 1.0000; alignment differs by at most 1 px.
- End to end: the engine started against sample videos with a real DB and Redis, and all cameras went IDLE → ACTIVE on motion (standards/11 checklist item 3).
- **Not verified** (no consented face data, cameras or reference server here):
  - accuracy, TAR/FAR (NFR-1, NFR-2, AC-1) — `evaluate.py` exists but was not run;
  - recognition of real faces end to end, and event latency (NFR-3);
  - capacity of 8 entrance + 8 general cameras on 16 cores (NFR-4), and the 72-hour soak (Phase 2 gate);
  - real RTSP cameras, sub-streams and GOP;
  - liveness (no model file);
  - ArcFace weights (licence);
  - INT8 conversion (needs calibration data);
  - the ladder under real overload — logic is tested with forced load, and the soak never left level 1.

## Notes
- Finding: on AMX/AVX-512-bf16 Xeons, OpenVINO's CPU plugin defaults to **bf16**. That shifted YuNet landmarks by up to 5 px and lowered SFace cosine to 0.9996. The engine forces f32 (`ENGINE_OPENVINO_PRECISION`); bf16 must pass `evaluate.py` before use.
- Finding: the stock `onnxruntime` wheel ships an Azure (remote) execution provider. The engine always passes `providers=["CPUExecutionProvider"]`.
- Finding: the open-source MinIO server is archived, and its images and binaries return "410 Gone". Storage now sits behind `facetrack_common.storage` with a local-volume default and an S3 backend (ADR-0005, pending owner decision P2).
- Finding: `supervision` deprecated `ByteTrack` (removed in 0.31). It is pinned `<0.31`; P9 asks for approval to move.
- Outside the listed layout (flagged per §0.4): `engine/app/db.py` (read-only session factory) and `engine/scripts/sample_video.py` (synthetic clips; no recordings of people exist).
- Models for all 16 tables were written in this phase because the engine reads cameras, enrollments and settings; the migration is in Phase 2.
- `enroll_folder.py` (requirements §20) was intentionally not built: enrolling outside the backend would bypass the consent check (standards/18).
- Unspecified thresholds were defaulted and are listed for confirmation (P8).
