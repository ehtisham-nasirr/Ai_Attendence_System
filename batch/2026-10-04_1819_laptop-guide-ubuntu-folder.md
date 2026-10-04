# Batch: laptop-guide-ubuntu-folder

**Date:** 2026-10-04 18:19
**Type:** other
**Command Used:** ad-hoc (documentation from the owner's laptop test)
**Standards Referenced:** standards/13-documentation-and-comments.md
**Requirements:** §18 (deployment)

## Summary
The local-development guide now records what the owner's first full laptop run showed:
- **Project folder:** the project must live inside Ubuntu (`~/Ai_Attendence_System`), not on a Windows drive. The `mediamtx.yml` bind mount failed with "not a directory", and earlier photo and clip mounts failed too.
- **8 GB laptops:** they need a WSL memory limit plus swap. The Ubuntu terminal closed during the portal build and would not reopen.

## Changes Made
- **`docs/local-development.md`:**
  - Every path now points to `~/Ai_Attendence_System`; the D: drive is only used to receive the bundle.
  - Step 3: clone from the bundle into Ubuntu, and how to move an existing `/mnt/d` copy (Docker volumes carry over).
  - New step 2.1 for 8 GB RAM: `.wslconfig` with 4 GB plus 8 GB swap, `ENGINE_DEV_MEMORY=2g`, `WEB_CONCURRENCY=1`.
  - Certificate trust: copy the certificate to D: first, then run `certutil`.
  - Clip copy from `Camera Roll`.
  - Git Bash steps removed (Ubuntu's openssl is enough).
  - Two new troubleshooting rows: the terminal closing from out-of-memory, and `not a directory` mount errors.
- **`engine/README.md`:** clips are copied into the `videos` volume.

## Files Changed
```
docs/local-development.md
engine/README.md
```

## Database Changes
None.

## CPU / Performance Impact
N/A.

## Testing
Documentation only. Every command and fix in it comes from the owner's run today, as reported in their terminal output:
- the move to `~/Ai_Attendence_System` brought all services up, including mediamtx;
- recognition marked "Ehtisham Nasir" with scores 0.52–0.79;
- the Attendance screen showed a weekly-off day with check-in 16:59 and check-out 18:15.

The `.wslconfig` values were applied on the 8 GB laptop and the next build completed.

## Notes
Snapshots taken before the move to Docker volumes are missing ("?" tiles in Unknown faces). That is old test data; dismissing those groups is enough.
