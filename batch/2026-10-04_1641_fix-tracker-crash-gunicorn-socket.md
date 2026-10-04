# Batch: fix-tracker-crash-gunicorn-socket

**Date:** 2026-10-04 16:41
**Type:** bugfix
**Command Used:** commands/fix-bug.md, commands/engine-change.md
**Standards Referenced:** standards/10-python-standards.md, standards/11-testing.md, standards/17-recognition-engine-cpu.md
**Requirements:** FR-4 (camera processing must recover, not crash), §10.1 step 5 (tracking), §18 (deployment)

## Summary
Two defects found by the owner's first local test with a real webcam clip:
- **Engine crash:** every camera process crashed with `KeyError: 'index'` as soon as a frame produced no confirmed ByteTrack track. This happens, for example, when a face's score is below the activation level, or a new face is not yet confirmed. The supervisor restarted the camera and it crashed again, so recognition never ran.
- **Backend startup error:** the backend logged `Control server error: Permission denied: '/home/facetrack'` at startup.

## Changes Made
- `engine/app/pipeline/tracking.py`: when ByteTrack returns no tracks (an empty `Detections` without our `index` data), `FaceTracker.update` returns an empty list. Previously it indexed the missing key. Thresholds and tracker parameters are unchanged.
- `engine/tests/test_tracking.py` (new): tests against the real `supervision` ByteTrack, not a fake:
  - the same face keeps its track id;
  - frames with only a low-score or unconfirmed face return nothing;
  - tracking continues after an empty frame.

  Two of the three fail without the fix.
- `backend/gunicorn.conf.py`: `control_socket_disable = True`. Gunicorn 26's runtime control socket is unused, and it tried to create `~/.gunicorn` for the system user, which has no home directory.

## Files Changed
```
engine/app/pipeline/tracking.py
engine/tests/test_tracking.py
backend/gunicorn.conf.py
```

## Database Changes
None.

## CPU / Performance Impact
`FaceTracker.update` was measured over 3,000 updates on the dev container: about 0.49–0.56 ms per update after the fix and about 0.50 ms before. The difference is within run-to-run noise; the change adds one length check and one key lookup per processed frame. Camera processes no longer crash and restart on such frames, which removes the restart cost entirely.

## Testing
- **Engine:** 113 passed, 2 skipped (`uv run pytest`); ruff, ruff format and mypy are clean. The crash was reproduced with a script feeding real ByteTrack the same kind of frames: frames 3 and 5 raised `KeyError: 'index'`.
- **Gunicorn:** the backend image started with the new config. The control-server error is gone, and two workers report "Application startup complete".
- **Not verified here:** recognition end to end with a real face. That needs the owner's rebuilt engine image and their enrolled face (no real faces in this repository or sandbox).

## Notes
- The owner's log also showed `PermissionError: /srv/media/enroll` during enrollment. That is a local Docker/WSL media-folder permission issue and is fixed separately.
- `supervision` still warns that ByteTrack is deprecated (P9 in docs/open-questions.md).
