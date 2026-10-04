# Batch: unknown-faces-group-cards-ui

**Date:** 2026-10-04 19:20
**Type:** feature
**Command Used:** commands/new-feature.md (frontend part; the backend part is `batch/2026-10-04_1909_unknown-groups-bulk-snapshot-pruning.md`)
**Standards Referenced:** standards/07-frontend-architecture.md, standards/08-frontend-state-and-api-layer.md, standards/09-forms-errors-logging.md, standards/11-testing.md
**Requirements:** FR-27, §13 screen 9 (Q58)

## Summary
The Unknown faces screen now shows one card per group of similar faces over the whole queue, not per page. In the owner's test his own face filled 3–4 pages of cards. A card's decision now covers all its faces in one request.

## Changes Made
- **Page:** lists groups from `GET /api/v1/unknown-faces/groups`, 12 per page. Pagination counts groups.
  - Each card shows the face count, first and last seen (or "Seen" for one face), the cameras, and up to 8 sample thumbnails.
  - A line shows "N faces in M groups". When `grouping.truncated` is set, a small note says only the newest faces are grouped.
  - Status and camera filters stay in the URL, as before.
  - If a decision empties the last page, the page moves back to the new last page.
  - The query key starts with `unknown-faces`, so `/ws/live` invalidations still refresh the list.
- **Assign dialog:** lists every face of the card, 24 per page, each with a tick box (all ticked by default). This meets the Q58 rule: the reviewer can see and untick each face before a bulk assign.
  - Only ticked ids are sent to `POST /api/v1/unknown-faces/bulk`, in the API's order, with the employee and the "Add to gallery" option.
  - Errors on `employee_id` and `consent_signed_at` appear under their inputs. Other errors appear in a toast.
- **Dismiss:** a confirmation ("Dismiss all N faces in this group?") then one bulk request with all face ids.
- **Results:** the API message is shown. Skipped faces turn it into a warning that gives counts ("1 already reviewed", "1 not found"). A gallery rejection is a separate warning. The unknown-faces, attendance and dashboard queries are refreshed.
- **Permissions:** Assign is shown only with `unknown_faces:assign`. Dismiss is shown to every reviewer. Groups with no pending faces show no actions.
- **`SecureImage`:** new optional `unavailableLabel`. When there is no snapshot, or it fails to load, it shows an icon and "No photo", and adds that text to the accessible name. Other screens are unchanged.
- **Hooks:** `useUnknownFaces` and the per-face `assign`/`dismiss` mutations were used only by this screen. They are replaced by `useUnknownFaceGroups` and a `bulk` mutation. The per-face API endpoints are unchanged.
- **`frontend/README.md`:** screen 9 line updated.

## Files Changed
```
frontend/README.md
frontend/src/components/common/SecureImage.tsx
frontend/src/components/unknown-faces/AssignDialog.tsx
frontend/src/components/unknown-faces/UnknownFaceGroupCard.tsx   (new)
frontend/src/hooks/useRecognition.ts
frontend/src/pages/unknown-faces/UnknownFacesPage.tsx
frontend/src/pages/__tests__/unknown-faces.test.tsx              (new)
```

## Database Changes
None.

## CPU / Performance Impact
N/A (no engine change). The page loads at most 12 cards × 8 thumbnails, lazily. The old page loaded up to 60.

## Testing
- **New Vitest + MSW tests (11, synthetic ids only):**
  - each group is shown once, with its count, times, cameras and 8 thumbnails;
  - "No photo" placeholder;
  - pages over groups, and moving back when a page is empty;
  - truncation note;
  - filters reach the API, and reviewed groups have no actions;
  - bulk assign sends only the ticked ids, with the employee and the gallery option, and reports skipped faces and the gallery rejection;
  - consent error under the gallery option;
  - dismiss after confirmation, with skipped faces reported;
  - an operator sees Dismiss but not Assign;
  - a `/ws/live` unknown event refetches the groups.
- **Frontend checks:** 74 tests passed. ESLint and `tsc` are clean. `npm run build` succeeded.
- **Not run:**
  - Playwright. `e2e/portal.spec.ts` only checks the "Unknown faces" heading, which is unchanged.
  - The live stack and the owner's laptop.
  - A visual check in a real browser.

## Notes
- Dismiss acts on every face of the card, as asked. Only assign lets the reviewer untick faces, as the Q58 contract requires.
- Snapshot availability is known only for the 8 samples. Other faces in the Assign dialog request their snapshot, and show "No photo" if it returns 404.
- The generated client (`src/api/generated`) was not edited by this task.
- A parallel task was editing `frontend/src/components/cameras/*` and `src/lib/cameraHints.ts` during this work. I did not touch them. They briefly gave one lint warning, which was gone on the final run.
