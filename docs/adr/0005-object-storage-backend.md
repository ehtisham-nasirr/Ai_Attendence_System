# ADR-0005: Object storage behind one interface; local volume by default

**Status:** Accepted for development, **pending owner confirmation for production** (docs/open-questions.md P2)
**Requirements:** §7, §8 ("MinIO (S3-compatible) or local disk"), NFR-8, NFR-9 · **Standards:** 14, 18

## Context
CLAUDE.md §1.2 and standards/14 name MinIO as the file store. While building (2026-10-03) we found
that the open-source MinIO server, client and KES projects are archived: `dl.min.io` answers
"410 Gone — no longer maintained, no security updates", and the `minio/minio` images are no longer
pullable. Running an unmaintained server that holds biometric snapshots is a security risk.
Requirements §8 already allows "MinIO (S3-compatible) or local disk".

## Decision
- `facetrack_common.storage.ObjectStore` is the single storage interface (used by the engine
  publisher and the backend `services/storage.py`). Callers always encrypt bytes first with the
  project encryption helper; object names are generated server-side and validated.
- Backends: `LocalObjectStore` (files under one managed root, a Docker volume shared by engine and
  backend containers) and `S3ObjectStore` (any S3-compatible server, through the `minio` client
  library, which is still a maintained S3 client).
- Default in `infra/docker-compose.yml`: `local`. Multi-server deployments need either a shared
  volume (e.g. NFS) for the media root or an S3-compatible server chosen by ITRC.

## Consequences
- No dependency on an unmaintained server. Snapshots stay encrypted at rest either way.
- The owner must choose the production store (local/NFS vs a maintained S3-compatible server).
- The `minio` container listed in requirements §18 is not shipped; the compose file documents how to
  point the stack at an S3-compatible service instead.
