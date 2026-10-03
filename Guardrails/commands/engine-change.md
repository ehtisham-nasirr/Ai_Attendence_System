# /engine-change

Use this for **any** change to the recognition engine: pipeline steps, camera modes, decoding, scheduling, the degradation ladder, models, thresholds/voting, the gallery, or the event contract (e.g. "add sub-stream support", "switch embedder to SFace", "tune the motion gate", "add a field to recognition events").

## Before Starting

1. Read `CLAUDE.md` §1.3 (CPU only; false accept is worse than a miss).
2. Read `standards/17-recognition-engine-cpu.md` in full.
3. Read requirements §9, §10.1 and §10.4, plus any FR/NFR the change touches.
4. If the change affects the event contract (`common/facetrack_common/events.py`), also read `standards/02-backend-architecture.md` § Event Consumer — the backend consumer must change in the same task.

## Steps

For `$ARGUMENTS` (the engine change):

1. **State the goal and the risk.** Which requirement does it serve? Could it affect accuracy (TAR/FAR), CPU usage, latency, or smoothness (backlogs, freezes)? If it changes thresholds, margin, voting or liveness behaviour, **stop and get explicit approval** before coding.
2. **Baseline.** Run `scripts/benchmark_cpu.py` on the reference clips and record: per-step ms (decode, motion, detect, embed, liveness), CPU % per camera in IDLE and ACTIVE, cameras per node, p95 latency. If accuracy could be affected, run `scripts/evaluate.py` and record TAR/FAR.
3. **Implement the smallest change** inside the correct module (`capture/`, `scheduler/`, `pipeline/`, `models/`, `gallery/`, `publisher/`). Keep:
   - latest-frame-only buffers and bounded queues,
   - best-crop-only embedding and track locking,
   - fixed thread budgets per worker,
   - the change inside the degradation ladder if it adds CPU work,
   - all new tunables in configuration, not constants.
4. **Contract changes:** if the event schema changes, make the change additive (new optional fields), update `common/`, the backend consumer and its tests in the same task.
5. **Tests:** unit tests for the changed logic; state-machine/degradation tests if scheduling changed.
6. **Measure again.** Re-run the benchmark (and evaluation if relevant) on the same clips and server. The change is not done if:
   - CPU per camera or p95 latency got worse without an agreed reason, or
   - FAR increased, or TAR dropped beyond the agreed tolerance.
7. **Soak check:** run the engine for at least 30 minutes on looped clips and confirm no memory growth and no growing lag.
8. **Create a batch log file in `batch/`** per `CLAUDE.md` §7 with `Type: engine-change` and the before/after numbers in **CPU / Performance Impact**.
9. **Report** using the Final AI Response Format in `CLAUDE.md`, including the before/after table.

Never present an estimated number as measured. If the reference server or clips were not available, say so and mark the numbers as unverified.
