# ADR-0006: Known-but-short tracks are not logged as Unknown

**Status:** Accepted (owner decision, 2026-10-04)
**Requirements:** FR-17, FR-18, FR-27, NFR-2, §10.1 step 9
**Amends:** `docs/requirements.md` §10.1 step 9 and `Guardrails/standards/17-recognition-engine-cpu.md` §6 ("otherwise it becomes Unknown when the track ends")

## Context
During laptop testing the owner's own face filled the Unknown faces screen. Most cards came from tracks that were too short to collect 3 crops, or that got only 1 vote, although every crop matched him. FR-17 asks that faces *below the match threshold* are logged as Unknown; these faces were above it, for exactly one employee.

The owner's words (2026-10-04): "jo tm mashrwa dy rhy wo b dekh lo" ("look at the suggestion you are giving as well"). This was in reply to the proposal to stop logging such tracks as Unknown, in the same message that asked for one Unknown card per person.

## Decision
- An unconfirmed track is **not** logged as Unknown when all of these hold (`points_to_one_employee`):
  - at least one crop passes threshold and margin;
  - every crop that passes names the same employee;
  - no crop scores any other employee at or above the threshold.
- Such a track emits nothing: no event and no snapshot. The engine counts it in `facetrack_engine_unconfirmed_known_tracks_total{camera_id}`.
- **Exceptions, still logged as Unknown:**
  - tracks on cameras that require liveness (entrance), because a brief photo or screen there never reaches the liveness check, and its snapshot is the audit evidence;
  - spoofs caught by liveness;
  - tracks whose inference requests were given up.
- Confirmation is unchanged: 2 of 3 crops, threshold, margin, no other employee at threshold (NFR-2). This decision never marks anyone present.

## Consequences
- **No review for skipped tracks (FR-27).** A skipped track never reaches the Unknown review queue. If it was an employee's only sighting of the day, HR uses a normal attendance correction.
- **Strangers who resemble one employee.** A stranger whose crops match only one employee is skipped, not logged. He is still never marked present.
- **Monitoring.** The counter shows how often tracks are skipped, per camera.
- **Documents.** `docs/requirements.md` is a verbatim copy of the requirements document and is not edited. This ADR is the record of the change.
