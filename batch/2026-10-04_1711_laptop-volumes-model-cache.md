# Batch: laptop-volumes-model-cache

**Date:** 2026-10-04 17:11
**Type:** bugfix
**Command Used:** commands/fix-bug.md, commands/engine-change.md
**Standards Referenced:** standards/01-project-structure.md, standards/12-git-standards.md, standards/13-documentation-and-comments.md, standards/17-recognition-engine-cpu.md
**Requirements:** §18 (deployment), §15 (on-premise)

## Summary
Follow-up to `add-laptop-dev-engine-overlay`, based on the owner's test on Windows with Rancher Desktop and WSL:
- **Media and clips:** bind mounts of a Windows drive (`/mnt/d/...`) failed. The backend got `Permission denied: '/srv/media/enroll'`, the engine got `PermissionError` when saving snapshots, and the engine sometimes did not see the test clip at all. On a laptop, media and clips now live in Docker volumes.
- **Engine rebuild:** rebuilding after a code change downloaded the face models again. The owner's office network (Kaspersky HTTPS inspection) broke that download with `CERTIFICATE_VERIFY_FAILED`. The models are now downloaded in a layer before the application code.
- **README:** the root `README.md` had been committed as UTF-16LE; it is now UTF-8.

## Changes Made
- **`infra/docker-compose.dev.yml`:**
  - Named volumes `media` and `videos`.
  - `migrate`, `backend`, `worker`, `scheduler` and `engine` mount `media:/srv/media`, which replaces the `MEDIA_DIR` bind mount on the laptop only.
  - The engine reads clips from the `videos` volume; clips are copied in with `docker compose cp`.
  - Production (`docker-compose.yml`, `docker-compose.engine.yml`) is unchanged and keeps `MEDIA_DIR` for NFS.
- **`engine/Dockerfile`:** `download_models.py` is copied and run right after the dependency install and before `COPY engine/app`. Models are now downloaded again only when the Dockerfile, the dependencies or `common/` change.
- **`docs/local-development.md`:**
  - Step 4 and the step 6 media check now describe the volume.
  - Step 9 adds the clip copy commands.
  - Daily use says when models are downloaded again.
  - The troubleshooting table has rows for the permission error, missing clips and the Kaspersky untrusted-certificate page.
- **`engine/scripts/sample_video.py`:** the docstring no longer claims `make dev` loops clips through MediaMTX.
- **`README.md`:** converted from UTF-16LE to UTF-8 (same text).

## Files Changed
```
infra/docker-compose.dev.yml
engine/Dockerfile
engine/scripts/sample_video.py
docs/local-development.md
README.md
```

## Database Changes
None.

## CPU / Performance Impact
None at runtime. Only the image layer order changed; the image content is the same.

## Testing
- **Compose:** `docker compose -f docker-compose.yml -f docker-compose.dev.yml config` with the example env files, on a clean copy of `infra/`.
  - All five services resolve `/srv/media` to the `media` volume.
  - The engine also gets `engine-buffer` and `videos`.
  - The base compose still uses the bind mount.
- **Volume ownership** (real images, new volume):
  - First mounted by the backend image: `/srv/media` is owned by 10001.
  - The engine image (uid 10001) wrote `snapshots/`, and the backend image wrote `enroll/`.
  - `docker cp` into a `videos` volume works, and the clip is readable.
- **Engine image:** built with the new Dockerfile; models present (YuNet, SFace). After a change to `engine/app/__init__.py` (reverted afterwards), the rebuild showed the `download_models.py` step as **CACHED**.
- **Unchanged suites:** engine 113 passed / 2 skipped. Frontend lint, typecheck, 56 tests and build pass.
- **README:** `file README.md` reports UTF-8.
- **Not verified:** the volumes on the owner's Rancher Desktop laptop; the owner will apply them with the update.

## Notes
The owner's current laptop setup still runs a manual `facetrack-engine` container; the update instructions replace it with the compose `engine` service. No data is lost: enrollment had not succeeded before, and the database is in its own volume.
