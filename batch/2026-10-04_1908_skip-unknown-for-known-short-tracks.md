# Batch: skip-unknown-for-known-short-tracks

**Date:** 2026-10-04 19:08
**Type:** engine-change
**Command Used:** commands/engine-change.md
**Standards Referenced:** standards/17-recognition-engine-cpu.md, standards/18-privacy-and-biometric-data.md, standards/10-python-standards.md, standards/11-testing.md, standards/13-documentation-and-comments.md
**Requirements:** FR-17, FR-15, FR-18, NFR-2, §10.1 step 9

## Summary
The owner tested with a looping webcam clip of their own face. The owner is enrolled and was recognised, but the Unknown faces screen still filled with the same face. Tracks that were too short for the 2-of-3 vote ended as Unknown, even when every crop matched the owner. Such a "known but unconfirmed" track now emits nothing. It is counted and logged instead. Nothing new becomes "recognized".

## Changes Made
- **The rule** (`app/pipeline/voting.py`, `points_to_one_employee`): an unconfirmed track is "known but unconfirmed" only when all three conditions hold:
  - at least one embedded crop casts a vote (`crop_vote`: best score >= threshold AND best - second >= margin);
  - every voting crop votes for the same employee;
  - no crop scores any other employee at or above the threshold.

  Threshold, margin, `min_votes` and `required_crops` are unchanged. `decide_track` is unchanged.
- **Where it applies** (`app/pipeline/track_manager.py`). There are two places where an unconfirmed track became an Unknown event. Both now go through `_end_unconfirmed`:
  1. `_end` with embedded crops. This covers two cases:
     - a track that ended while its vote was still pending (1–2 crops embedded, the owner's case);
     - a track the vote decided as `unknown` (3 crops).

     For the vote's `unknown` outcome the rule applies only to the "too few votes" case: one vote for A, and the other crops below threshold or margin with no other employee at threshold. Split votes, ties, another employee at or above the threshold, and "no vote at all" all stay Unknown.
  2. The `unknown_embedding` path. A track that ended before the embed trigger gets one embedding of its best crop. If that single crop votes for one employee and names no other at the threshold, nothing is emitted. Otherwise it is Unknown as before.
- **Paths left unchanged**:
  - Cameras that require liveness (entrance): every unconfirmed track is still Unknown. A brief photo or screen there never reaches the liveness check (added after review).
  - Spoof (`on_liveness`): still Unknown.
  - Liveness request give-up: still Unknown.
  - Embedding request give-up: a new `gave_up` flag on the track keeps it Unknown (fail safe). This holds even if a later end-of-track embedding matches one employee.
  - Tracks with no usable crop: still dropped silently.
- **Counting**: `TrackManager` returns a new `UnconfirmedKnownTrack(track_id, embedded_crops)` action instead of an `EmitEvent`. `CameraWorker` handles it:
  - counts it as `unconfirmed_known_tracks`;
  - logs one INFO line with `camera_id`, `track_id` and `embedded_crops` only, with no employee code, scores, embedding or image;
  - does not JPEG-encode a snapshot or encrypt an embedding.
- **Metric**: new Prometheus counter `facetrack_engine_unconfirmed_known_tracks_total{camera_id}` (`app/metrics.py`). The supervisor exports it from the camera status report. The same count also appears in the existing generic `facetrack_engine_camera_counts_total{name="unconfirmed_known_tracks"}`.
- `engine/README.md`: describes the Unknown rule and its exception, and adds a troubleshooting row for an enrolled person who appears neither recognised nor in Unknown faces.

## Files Changed
```
engine/app/pipeline/voting.py
engine/app/pipeline/track_manager.py
engine/app/pipeline/camera_worker.py
engine/app/metrics.py
engine/app/scheduler/supervisor.py
engine/tests/test_voting.py
engine/tests/test_track_manager.py
engine/tests/test_camera_worker.py
engine/README.md
```

## Database Changes
None. The recognition-event contract is unchanged; fewer Unknown events are sent.

## CPU / Performance Impact
All numbers are from the dev sandbox (4 vCPU x86_64, OpenVINO), not the reference server. The old code was a copy of `HEAD` taken with `git archive` and run with the same venv and the same scripts.

**Changed path: micro-benchmark** (scratchpad `bench_track_end.py`). Each scenario runs 5,000 tracks per run, 5 runs, and reports the median of per-run medians. The timer covers `TrackManager.step` (track end) or `on_embeddings`, plus `CameraWorker._handle_actions`. That includes the real JPEG encode of a 256x256 snapshot, embedding encryption and building the event. Logging uses the project JSON formatter at INFO. The emitter is a no-op. Two full repeats gave:

| Scenario (per ended track) | Before | After |
|---|---|---|
| Short known track, 2 crops vote A (owner's case) | 182–187 µs (p95 220–233) | 32 µs (p95 46) |
| Short known track, 1 end-of-track embedding votes A | 181–184 µs (p95 226–234) | 30 µs (p95 44–51) |
| Short track below threshold (still Unknown) | 182–183 µs (p95 217–227) | 181–191 µs (p95 208–240) |
| 1 end-of-track embedding below threshold (still Unknown) | 184–188 µs (p95 229–276) | 183–185 µs (p95 211–224) |

- The new check alone (`points_to_one_employee`, 3 crops) costs 1.4–1.5 µs per ended track. `decide_track` costs 5.0–5.6 µs. Both were measured with `timeit`.
- The Unknown path did not change measurably (differences are within run-to-run noise).
- Not measured: the work no longer done downstream for each skipped track. That is the publisher thread (snapshot encryption, storage write, Redis XADD) and the backend (event and Unknown rows, snapshot file).

**Standard benchmark** (`scripts/benchmark_cpu.py --runtime openvino`, before and after). None of the steps it measures were changed. The before → after means were:
- full decode 2.4 → 2.2 ms;
- ROI detection 11.4 → 9.6 ms;
- 3-crop embedding 36.8 → 17.6 ms;
- motion gate 2.6 → 2.5 ms;
- camera CPU: IDLE 4.9 → 4.3 % and ACTIVE 19.5 → 16.6 % of one core, at 1.0 / 3.6 processed FPS.

These differences come from load on the shared sandbox (other agents were building and testing at the same time). They are not an effect of this change, and no improvement is claimed from them.

**Accuracy:** `scripts/evaluate.py` was not run (no consented evaluation set in the sandbox). TAR/FAR cannot change: `decide_track` and the threshold, margin and vote values are untouched, and the new rule only removes Unknown events. It never produces a `recognized` event. Tests prove this.

**Soak** (31 minutes, scratchpad `soak_track_end_clear.py`). The soak drove the real `CameraWorker`, real ByteTrack and `TrackManager` with scripted detector and embedder models. It used a fake clock with 0.3 s ticks. Three synthetic visitors cycled:
- a 2-frame visitor matching A;
- an 8-frame visitor matching A;
- a 2-frame visitor matching nobody.

Results:
- 17,481 cycles (52,443 tracks, 4.09 M ticks).
- Every short known visitor was counted and none emitted an event. Every confirmed visitor gave 1 recognized event. Every stranger gave 1 Unknown event.
- RSS was 191.7 MB at start and 192.0 MB from minute 1 to minute 30.
- The track table, pending requests and deferred queue were 0 at every sample.
- The old code under the same driver for 3 minutes: RSS 191.9 → 192.3 MB, with 2 Unknown events per cycle (the short known visitor also became Unknown).

A first soak attempt grew to 4.2 GB. tracemalloc traced this to the test doubles, not the engine. `InProcessClient.submitted` keeps every task with its image, and `FakeSource` records every call. The driver now clears those lists each cycle. This is a logic soak, not a full-engine soak: no decoder, inference pool, Redis or PostgreSQL. Frame lag cannot be measured with a fake clock.

## Testing
- Engine: 127 passed, 2 skipped (`uv run pytest`). The baseline was 113 passed, 2 skipped. Ruff, ruff format and mypy (`app`) are clean.
- One run during the soak had 2 failures in timing tests: the gallery match under 10 ms and the inference worker round trip. Load average was about 6 on 4 cores. Both tests cover untouched code, and both pass on a quieter machine.
- New unit tests (`tests/test_voting.py`, `tests/test_track_manager.py`):
  - a short track whose crops all match one employee, ended while the vote is pending → no event, `UnconfirmedKnownTrack`;
  - the same with one end-of-track embedding → no event;
  - a full track with 1 vote of 3 and no other employee → no event;
  - below threshold → Unknown as before;
  - two different employees → Unknown;
  - another employee at the threshold in a non-voting crop → Unknown;
  - margin not met → Unknown;
  - a spoof of a face matching one employee → Unknown;
  - a short track on a liveness camera → Unknown;
  - embedding given up after failures → Unknown;
  - the rule itself, including that it never confirms.
- New worker test (`tests/test_camera_worker.py`): real ByteTrack with scripted models. Two crops match A, then the person leaves. It checks:
  - no event is emitted;
  - the `unconfirmed_known_tracks` count is 1;
  - the INFO log has ids and counts only;
  - `facetrack_engine_unconfirmed_known_tracks_total{camera_id="3"}` goes up by 1 through `EngineSupervisor._export_metrics`.

  Against the old code this test fails: it emits the Unknown event the owner saw.
- One existing test was changed on purpose. `test_fr17_short_track_without_embedding_gets_one_embed_then_unknown` used a score of 0.9 for A, which asserted exactly the behaviour this change replaces. It now uses 0.30 (below threshold) and still checks one embed followed by Unknown. The 0.9 case moved to the new "emits nothing" test.
- Not tested here: a real face end to end. That needs the owner's rebuilt engine image and the enrolled face; the sandbox has no real faces.

## Notes
- **Owner approval:** the owner answered the proposal with "jo tm mashrwa dy rhy wo b dekh lo" (2026-10-04). The decision, and its amendment of `docs/requirements.md` §10.1 step 9 and standards/17 §6, are recorded in `docs/adr/0006-known-short-tracks-not-unknown.md`. standards/17 §6 now points to the ADR. `docs/requirements.md` is a verbatim copy and is not edited.
- **Review fix:** the first version also skipped short tracks on liveness cameras, so a brief spoof of an enrolled face left no evidence. Those cameras now keep every unconfirmed track as Unknown (`test_fr18_short_track_on_liveness_camera_is_still_unknown`).
- **Trade-off (FR-27):** a skipped track never reaches the Unknown review queue. So a reviewer cannot use FR-27 to assign it to the employee (to create attendance from it) or add its snapshot to the gallery. If an employee's only sighting of the day was such a short track, HR must use a normal attendance correction. The counter shows how often this happens per camera.
- **Strangers who resemble an employee:** a stranger whose crops match only one employee above threshold and margin is now also skipped instead of being logged as Unknown. They are still never marked present.
- **No configuration switch:** none was added, because the task defined the rule exactly. If the owner wants it per camera or switchable, that is a new setting and needs the backend `settings` table.
- Grafana and alerts were not changed (infra is outside this task). A panel for the new counter would be useful.
