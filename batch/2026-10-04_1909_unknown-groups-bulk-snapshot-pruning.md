# Batch: unknown-groups-bulk-snapshot-pruning

**Date:** 2026-10-04 19:09
**Type:** feature
**Command Used:** commands/new-feature.md (backend part)
**Standards Referenced:** standards/02-backend-architecture.md, standards/03-fastapi-coding-standards.md, standards/04-rest-api-standards.md, standards/05-database-postgresql.md, standards/11-testing.md, standards/13-documentation-and-comments.md, standards/15-business-logic-and-duplication.md, standards/16-change-management-and-workflow.md, standards/18-privacy-and-biometric-data.md
**Requirements:** §13 screen 9, FR-16, FR-17, FR-23, FR-27, FR-28, FR-37, FR-39, §10.3 duplicate suppression, NFR-2, NFR-7

## Summary
In the owner's laptop test, his own face filled 3–4 pages of the Unknown faces screen. Grouping was done per page, so the same person came back as a new card on every page. The backend now groups the whole queue, one card per person, and can decide a whole card in one request. When a day closes, repeat sightings inside the §10.3 duplicate window lose their photo, so fewer photos are stored.

## Changes Made
- **New `GET /api/v1/unknown-faces/groups`:**
  - same filters as the per-face list; pagination counts groups; newest activity first;
  - groups every matching face, not one page; at most the newest 5,000, and `grouping.truncated` says when older faces were left out;
  - each card has a stable `group_id` (its oldest face), counts, first/last seen, cameras, all `face_ids` and up to 8 samples (with snapshot first);
  - viewing is audit-logged (`unknown_face.view_queue`, `view: groups`).
- **Grouping method (`domain/recognition/grouping.py`, Q58):**
  - compares each face with each group's centre at the model's match threshold, oldest first;
  - deterministic; decryption and comparison run off the event loop;
  - the per-face list uses the same code for its `group_id`. That endpoint is otherwise unchanged.
- **New `POST /api/v1/unknown-faces/bulk`:**
  - takes `face_ids` and `assign` or `dismiss`; one transaction; each attendance day is rebuilt once;
  - faces that are gone or already reviewed are skipped and reported;
  - same permissions as the single actions; one audit entry per face, with no biometric data;
  - "Add to gallery" uses the first assigned face with a snapshot (Q43).
- **Fewer photos (Q59), at day close:**
  - every event keeps its photo while its day is open;
  - when the FR-23 job closes a day, a recognised sighting inside the cooldown after the last photo kept on the same camera, in the same work day, loses its photo; the row stays and the object is deleted after the commit;
  - always kept: the day's counted check-in and check-out, voided events, and events that came from an unknown face (shared object);
  - `snapshot_available` is then false in the event log; `/ws/live` is unchanged;
  - each close run that prunes writes one `retention.delete` audit entry with the count;
  - unknown faces are never pruned; a re-sent object for an event that has no photo is deleted.
- **`attendance.apply_recognitions`:** rebuilds each affected day once. `apply_recognition` now calls it; its behaviour is unchanged.
- **Docs:** `docs/openapi.yaml` and the generated portal client were regenerated. Q58, Q59 and Q60 were added to `docs/open-questions.md`. Q60 is written on behalf of the parallel engine change.

## Files Changed
```
backend/app/api/v1/recognition.py
backend/app/domain/attendance/service.py
backend/app/domain/recognition/grouping.py        (new)
backend/app/domain/recognition/service.py
backend/app/repositories/event_repo.py
backend/app/schemas/recognition.py
backend/app/services/storage.py
backend/tests/api/test_recognition_dashboard.py
backend/tests/domain/test_event_processing.py
backend/tests/domain/test_unknown_grouping.py     (new)
docs/openapi.yaml
docs/open-questions.md
frontend/src/api/generated/endpoints.ts
frontend/src/api/generated/model/*                (14 new files, index.ts)
```

## Database Changes
None. No model or migration change.

## CPU / Performance Impact
N/A for the engine.
- **Backend grouping:** one core, in a worker thread (dev container, synthetic vectors, decryption included). 5,000 faces of 50 people: about 90 ms (128-d) and 105 ms (512-d). Worst case, 5,000 different people: about 0.36 s (SFace, 128-d) and 1.3 s (`arcface_r50`, 512-d). It runs on every page view and live refresh.
- **Day close:** one extra query per closed employee-day. Event ingest has no extra query.

## Testing
- **Backend:** 173 passed (17 new). Ruff, ruff format and mypy are clean.
- **New tests:**
  - grouping: a drifting person stays in one card, deterministic, stable ids, models kept apart, no merge below the threshold;
  - groups API: one card across pages, samples, sort, truncation, filters, 401/403/422, audit entry;
  - bulk: assign and dismiss, 403 for an operator assigning, 422 cases, consent, skipped faces, gallery, attendance, one audit entry per face;
  - photo pruning at day close: nothing pruned while open; counted check-in/check-out keep photos, also inside the window; per-work-day boundary for a day and a night shift; void and FR-27 assign before close; an assigned face keeps its shared object; same result in every arrival order and no event row lost; audit count; idempotent; a re-sent object; the event log and snapshot 404.
- **Frontend:** ESLint, `tsc`, 76 tests and `npm run build` pass with the regenerated client (unchanged by the review fixes).
- **Not verified:**
  - the live stack (`make dev`) and the owner's laptop;
  - real unknown faces (only synthetic vectors).
- **Environment:** dockerd was not running and was started for testcontainers.

## Notes
- **Flagged per §0.4 (needs the owner's confirmation):**
  - `POST /unknown-faces/bulk` is an action URL that §12 does not list;
  - the groups response adds a top-level `grouping` object to the standards/04 list envelope;
  - photo pruning is always on (no setting).
- **Grouping risk:** a wrong face can pull a group toward a second person (Q58). The portal must show all faces of a card, or let the reviewer remove faces, before a bulk assign.
- **Portal pages not changed here:** the Unknown faces page still uses the per-face list. The frontend change is a separate task.

## Review fixes (same unit of work)
- **Pruning crossed the day boundary (major):** fixed. Pruning now runs per work day, at day close, inside `day_window`.
- **Void or FR-27 assign after pruning (major):** fixed for changes before the day closes. Pruning waits for the close and never touches the counted events. A change after the close can still leave the new counted sighting without its own photo. This is listed in Q59 and P14 for the owner.
- **Grouping cost understated (minor):** fixed. Under load, the multi-threaded BLAS product took 6–16 s and every core for 5,000 different 512-d faces. It now uses `einsum` on one core, with the same groups (about 1.3 s). Q58 and this log give the measured worst case.
- **`POST /unknown-faces/bulk` and the `grouping` field (minor):** not changed in code. They are left for the owner to confirm as P14, with a fallback if refused.

