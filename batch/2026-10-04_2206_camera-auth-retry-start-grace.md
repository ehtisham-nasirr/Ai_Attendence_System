# Batch: camera-auth-retry-start-grace

**Date:** 2026-10-04 22:06
**Type:** engine-change
**Command Used:** commands/engine-change.md
**Standards Referenced:** standards/17-recognition-engine-cpu.md (§8 Resilience), standards/10-python-standards.md, standards/11-testing.md, standards/13-documentation-and-comments.md
**Requirements:** FR-4, standards/17 §8 (decision Q61)

## Summary
When a camera refuses the login (RTSP 401/403), the engine now waits 15 minutes (configurable) before the next login instead of retrying every 2–60 s. A Dahua camera locks the account after a few failures, so the old retries kept it locked. A new camera process now gets a 120 s start grace for its first status report. The supervisor used to call it hung after 30 s and restart it before it had started. That restart loop also kept edited cameras showing "Offline".

## Changes Made
- `EngineSettings`: added `auth_retry_s` (default 900, min 60; `ENGINE_AUTH_RETRY_S`), `camera_hung_after_s` (30, the old constant) and `camera_start_grace_s` (120).
- Decoder: `av.error.HTTPUnauthorizedError` / `HTTPForbiddenError` set `last_error` and log "camera refused the credentials; waiting before the next attempt" with `retry_in_s`. The next attempt is after `auth_retry_s`. Other errors keep the FR-4 2 s → 60 s backoff. `stop()` still ends the wait at once. A saved link change restarts the camera process (config fingerprint), so it is tried at once.
- Supervisor: `_is_hung()` uses the start grace until the first report, then the 30 s limit. `_HUNG_AFTER_S` was removed (now config).
- `infra/env/engine.env.example`, `docs/runbook.md` (CameraOffline), `docs/open-questions.md` Q61.

## Files Changed
```
engine/app/config.py
engine/app/capture/decoder.py
engine/app/pipeline/camera_worker.py
engine/app/scheduler/supervisor.py
engine/tests/test_decoder.py
engine/tests/test_scheduler.py
infra/env/engine.env.example
docs/runbook.md
docs/open-questions.md
```

## Database Changes
None.

## CPU / Performance Impact
Measured on the owner's laptop. The engine container is limited to 2 CPUs and 2 GB, with 4 cameras. These are not reference-server numbers.

**Root cause, measured with the old code.** A scratchpad harness ran the real `run_camera_process` in a spawned process against a local fake RTSP server that answers 401/403/404. It did not touch the real camera.
- The time to the first status report was 31.8 s, 13.9 s and 17.7 s in three runs. Interpreter start took about 2.7 s and the imports about 10 s. The engine container was at about 95 % CPU.
- Engine log, 16:19–16:24 PKT: ReceptionCam (id 4) was restarted 7 times with `hung: true` after an edit.
- Login attempts in one process with the old decoder came at gaps of 2, 4, 8, 16 and 32 s. Each restart started the series again.

**After, measured in the real engine.** The patched image was deployed. A temporary camera row pointed at the fake 401 server inside the engine container. It was watched for 200 s and then deleted.
- 1 login attempt in 200 s. The old decoder makes 6 or more in the same time, before counting restarts.
- 0 "camera process failed" restarts.
- The log line "camera refused the credentials" carries `retry_in_s: 900`.

**Per-frame CPU:** no change. The decode, motion, detect and embed paths are not touched. The new work is one `isinstance` check per failed connection and one comparison per camera in the 2 s watchdog loop. `scripts/benchmark_cpu.py` was **not** re-run. The laptop had no reference clip, and the measured steps did not change.

**Soak:** the 30-minute soak was **not** run. The engine has been running on the patched image since 21:57 PKT.

## Testing
- Engine test suite in a local test image (`facetrack/engine:latest` plus the uv.lock dev group; not shipped):
  - before the change: 127 passed, 2 skipped, 1 failed;
  - after the change: 131 passed, 2 skipped, 1 failed.
  - The failure both times is `test_nfr5_5000_employees_match_under_10ms_per_face`: 77 ms and 175 ms on the busy laptop. That gallery code is untouched.
- Ruff check, ruff format and mypy (`app`) are clean.
- New tests:
  - `test_decoder.py`: 401 and 403 give exactly 1 connection in 2 s with `auth_retry_s=60`. `stop()` ends the wait in under 5 s. `last_error` has no credentials. 404 keeps the fast backoff (4 or more connections).
  - `test_scheduler.py`: no restart at 31 s before the first report; restart after the 120 s grace; the 30 s limit applies after a report.
- Not tested: a real Dahua lockout. The real cameras were not given wrong passwords on purpose.

## Notes
- FR-4 states "2 s up to 60 s". The owner chose on 2026-10-04 to treat 401/403 separately with a 15-minute wait (Q61). Network drops are unchanged.
- The rollback image is kept as `facetrack/engine:pre-q61`.
- Live-view (MediaMTX) pulls with a wrong password are not covered. They happen only while someone watches.
- While investigating, recognition on the real cameras was found starved. The single inference worker is busy with the looping test file on "PC Camera" (407 Unknown faces today). Detection on cameras 2 and 4 timed out (14 and 11 timeouts, 0 and 1 faces detected), and the ladder reached level 5 (embedding deferred). No code was changed for this. The owner was asked to disable PC Camera, as the handoff planned.
