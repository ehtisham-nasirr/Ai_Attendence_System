# Recognition Engine — CPU-Only Rules

The engine runs on the CPUs of existing data center servers. **There is no GPU.** These rules exist so the engine stays smooth, never builds a backlog, and never freezes — and so recognition stays accurate. They implement requirements §9, §10.1, §10.4, NFR-3, NFR-4 and NFR-15.

## 1. Core Principle

> Cheap work runs often; expensive work runs rarely; nothing queues without a limit.

- Motion detection (cheapest) runs while idle.
- Face detection (cheap) runs only when a camera is ACTIVE, only on the ROI, only at the configured rate.
- Embedding (expensive) runs only on the **best 3 crops per track**, never on every frame.
- A confirmed track is **locked** and consumes no more detection-to-embedding work.

## 2. Camera Modes (per-camera state machine)

| Mode | Enter when | What runs |
|---|---|---|
| `IDLE` | No motion in ROI | Keyframe-only decode (`skip_frame=nokey`), motion check on a 320 px frame |
| `ACTIVE` | Motion in ROI | Full decode; detection at camera FPS (default 4 entrance / 1 general); tracking; best-crop selection |
| `COOLDOWN` | No face and no motion for 3 s | Detection at 1 FPS; → `IDLE` after 10 s more, → `ACTIVE` on motion |
| `PAUSED` | Outside operating hours, or shed by the degradation ladder | Nothing processed |

- Mode logic lives only in `engine/app/scheduler/`. Do not scatter mode checks across pipeline code.
- Every mode change is a metric and an INFO log; it is published as `CameraStatusChanged`.
- Timings (3 s, 10 s, FPS values) come from configuration, not constants.

## 3. Frame Handling

- **Latest frame only.** Each decoder writes into a **1-slot buffer that overwrites** the previous frame. Processing always takes the newest frame. If processing is slow, frames are dropped — never queued.
- **No unbounded queues anywhere in the engine.** Every queue has a fixed `maxsize`, and the overflow policy (drop oldest / drop new) is explicit in code.
- Decoders use **PyAV** with keyframe-only mode while IDLE. Entrance cameras are configured with GOP ≤ 1 s.
- Use the camera **sub-stream** for general cameras and for idle motion checks where available; use the main stream for entrance cameras when ACTIVE.
- Crop the ROI before detection; never run detection on the full frame of an entrance camera.
- JPEG-encode snapshots only when an event is emitted.

## 4. Processes and Threads

- One **decoder process per camera**; a shared **inference worker pool** (separate processes) for detection, embedding and liveness. No frame processing in the FastAPI event loop.
- Each inference worker has a fixed thread budget (OpenVINO `INFERENCE_NUM_THREADS` / ORT `intra_op_num_threads`, default 2) and is pinned to cores. Set `OMP_NUM_THREADS` explicitly — never leave libraries to grab all cores.
- Total threads = workers × threads per worker ≤ physical cores reserved for the engine (configured per node).
- Face crops are sent to the pool in small micro-batches (≤ 8); do not wait more than 50 ms to fill a batch.

## 5. Models

- Models are hidden behind the `Detector`, `Embedder` and `LivenessChecker` interfaces in `engine/app/models/`. Swapping a model is a config change, not a code change.
- Sanctioned models: **YuNet** (detector, primary), SCRFD-500M/2.5G (alternative); **ArcFace R50 INT8 on OpenVINO** (embedder, requires InsightFace commercial licence), **SFace** (permissive fallback); **MiniFASNet** (liveness, once per confirmed track).
- Runtime: **OpenVINO** (primary) or **ONNX Runtime CPU**. Never add CUDA/TensorRT/GPU packages.
- INT8 conversion goes through `scripts/convert_int8.py` (NNCF); a converted model must pass the accuracy evaluation before use.
- Model files are downloaded by `scripts/download_models.py` and never committed.
- Embeddings from different models are never compared; the gallery is rebuilt when the embedder changes.

## 6. Recognition Decision

- Match with cosine similarity on L2-normalised vectors via FAISS (inner product).
- Accept only if best score ≥ `match_threshold` **and** (best − second-best employee) ≥ `margin`, per camera.
- A track is confirmed when **at least 2 of its 3 best crops** match the same employee and none match another above threshold; otherwise it becomes Unknown when the track ends.
- Liveness runs once on the best crop of a confirmed track on entrance cameras.
- Thresholds, margin and voting values are read from the `settings` table / camera row. **Never change their defaults, and never lower them, without explicit approval** (false accept is worse than a miss — NFR-2).

## 7. Degradation Ladder (load shedding)

The load monitor in `engine/app/scheduler/` samples CPU and per-camera lag every 5 s.

- Step **down** when CPU > 85% for 30 s or lag > 2 s; step **up** when CPU < 60% for 2 minutes.
- Steps: (1) normal → (2) general cameras 0.5 FPS → (3) general cameras PAUSED → (4) entrance cameras 2 FPS, liveness async → (5) embedding queued (bounded) and processed when load drops.
- Entrance cameras (`ENTRY`, `EXIT`, `ENTRY_EXIT`) always have priority over `GENERAL`.
- Each step change is logged, exposed at `/load`, exported as a metric and published as `LoadLevelChanged`.
- Do not add new ways for the engine to consume CPU without placing them in this ladder.

## 8. Resilience

- A **watchdog** restarts a decoder with no frame for 10 s; streams reconnect with exponential backoff (2 s → 60 s).
- A worker whose memory exceeds its limit is restarted; the pool keeps serving other cameras.
- If Redis is unreachable, events are written to a bounded local disk buffer and replayed in order; nothing is lost (NFR-7).
- One failing camera must never affect another.

## 9. Scaling

- The engine is stateless per camera. Cameras are assigned to nodes through `cameras.engine_node`; a node processes only its assigned cameras.
- All nodes share Redis, PostgreSQL and the gallery (reloaded on `/gallery/reload` or on an enrollment change notification).

## 10. Measurement Is Mandatory

- Every pipeline, model or scheduling change is measured with `scripts/benchmark_cpu.py` on a reference server (per-step ms, CPU %, cameras per node) and with `scripts/evaluate.py` for accuracy (TAR/FAR).
- Results go into the batch log. Never claim a performance improvement without numbers.
- Follow `commands/engine-change.md` for the full procedure.
