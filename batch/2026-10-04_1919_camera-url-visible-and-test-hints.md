# Batch: camera-url-visible-and-test-hints

**Date:** 2026-10-04 19:19
**Type:** bugfix
**Command Used:** commands/fix-bug.md
**Standards Referenced:** standards/07-frontend-architecture.md, standards/09-forms-errors-logging.md, standards/11-testing.md, standards/06-security-and-auth.md
**Requirements:** FR-2 (camera connection test), §13 screen 6

## Summary
The owner is adding real Dahua cameras and asked for two changes:
- **Visible URL:** the stream URL fields hid what he typed like a password. He asked for plain text.
- **Clearer test failure:** the connection test failed with a raw "401 Unauthorized" error and no explanation.

## Changes Made
- **`CameraForm.tsx`:**
  - The main and sub-stream URL inputs are `type="text"`, with spellcheck and auto-capitalise off.
  - The placeholder shows a Dahua example.
  - The help text says the URL is visible while typing, stored encrypted after saving, and never shown again.
  - The API stays write-only: a saved URL is never returned or prefilled.
- **`lib/cameraHints.ts` (new):** a plain-language hint next to the raw error for the three common RTSP failures:
  - 401: username or password rejected; URL-encode special characters; accounts lock after repeated failures.
  - 404: wrong stream path; Dahua and Hikvision examples.
  - Timeout, no route or refused: camera not reachable.
- **`CameraTestPanel.tsx`:** shows that hint below the raw error.
- **Tests:** `components/cameras/__tests__/CameraTestPanel.test.tsx` (4 tests).

## Files Changed
```
frontend/src/components/cameras/CameraForm.tsx
frontend/src/components/cameras/CameraTestPanel.tsx
frontend/src/lib/cameraHints.ts
frontend/src/components/cameras/__tests__/CameraTestPanel.test.tsx
```

## Database Changes
None.

## CPU / Performance Impact
N/A.

## Testing
- The 4 new tests pass.
- ESLint is clean on the changed files, and `tsc -b --noEmit` passes.
- **Not verified:** the full portal suite and build in this commit. A parallel Unknown-faces change was in progress in other files. They are run again before the next push.

## Notes
- The 401 itself comes from the camera: the username or password in the URL is wrong or not URL-encoded. No code change can fix that; the hint tells the owner what to check.
- Showing the URL while typing was the owner's explicit choice. It is a shoulder-surfing trade-off. A dedicated camera user with live-view rights only limits the damage.
