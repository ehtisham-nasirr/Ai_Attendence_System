# Batch: camera-test-saved-link-403-hint

**Date:** 2026-10-04 19:33
**Type:** bugfix
**Command Used:** commands/fix-bug.md
**Standards Referenced:** standards/07-frontend-architecture.md, standards/09-forms-errors-logging.md, standards/11-testing.md
**Requirements:** FR-2

## Summary
In the edit drawer, "Test connection" tested the saved stream link while the screen showed a newly typed, unsaved link. While testing a Dahua camera, the owner typed the correct link, clicked Test without saving, and got the old link's error (403). The test is now blocked until the link is saved, a saved new link is tested automatically, and a 403 gets an explanation.

## Changes Made
- `CameraTestPanel` takes `disabledReason` instead of `disabled`, and shows the reason under the button.
- `CameraForm`:
  - blocks Test connection while a typed main or sub-stream link is not saved ("Save changes first: Test connection checks the saved stream link, not the one typed above.");
  - after saving a changed main link, runs the test automatically, as it already did on create (FR-2).
- `connectionHint`: new hint for 403 Forbidden. It explains that Dahua-style cameras lock the account for a while after several wrong passwords, and that FaceTrack keeps retrying a saved wrong link. The fix is to save the correct link, or turn the camera off, then wait or restart the camera. It also asks to check the user's live-view permission.

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
N/A (portal only).

## Testing
- `npx vitest run src/components/cameras`: 6 passed. New tests cover the 403 hint, and check that the test button is disabled with the reason shown.
- `npm run typecheck`: passes.
- `eslint` on the changed files: passes.
- Not tested: the edit drawer flow in a browser (type a link → blocked → save → auto-test) against a real camera.

## Notes
- The backend and engine are unchanged. The engine still tests the stored link (`POST /cameras/{id}/test`), so the stream link is never sent unencrypted to a test endpoint.
- **Not fixed here:** the engine keeps retrying a camera whose saved link has a wrong password (reconnect backoff 2 s → 60 s). On cameras with a lockout policy, that can keep the account locked. A longer wait after a 401/403 is the follow-up.
