# Privacy & Biometric Data

Face images and embeddings are **biometric personal data**. These rules implement requirements §15, FR-13, FR-39, NFR-8 and NFR-9, and apply to every package. When in doubt, choose the option that stores less, keeps it shorter and exposes it to fewer people.

## Consent

- Enrollment (photo upload, webcam capture, bulk import, adding an Unknown face to a gallery) is **blocked** unless `employees.consent_signed_at` is set. Enforce this in the backend domain service, not only in the UI.
- An employee without consent can still be in the system for manual/alternative attendance.

## Data Minimisation

- **Never store raw video.** The engine keeps frames in memory only; the NVR's recording is outside FaceTrack.
- Store only: embeddings, enrollment photos, and small face crops (snapshots) for events and unknown faces.
- Purpose limitation: biometric data is used **only** for attendance and its audit. Do not build features for performance monitoring, behaviour, emotion, age or movement analytics (explicitly out of scope).
- Do not send biometric data, video or employee data to any external or cloud service, including AI APIs.

## Protection

- Embeddings, camera credentials and snapshots are encrypted at rest (AES-256) using the project's encryption helper — do not invent a new scheme or store keys in code or Git.
- Snapshot and enrollment images are served to the portal only through authenticated, permission-checked backend endpoints (short-lived signed URLs from MinIO are acceptable) — never public bucket URLs.
- Biometric data never appears in logs, error messages, metrics labels or batch logs.

## Retention and Erasure

- Retention periods come from the `settings` table (defaults: event snapshots and unknown faces 90 days; enrollment data until employee exit + 30 days). The scheduled `retention` Celery task deletes expired data automatically (FR-39).
- **Deactivating** an employee stops recognition immediately (gallery reload); **biometric erasure** (`DELETE /employees/{id}/biometrics`) hard-deletes enrollments, photos, embeddings and related snapshots, then reloads the gallery (FR-13).
- Erasure and retention deletes are hard deletes — not soft deletes — and are written to the audit log (who, when, what was erased, without the data itself).

## Access and Audit

- Only roles listed in requirements §4 may view live video, snapshots, galleries or unknown faces; managers see only their department.
- Every enrollment, gallery change, erasure, export and viewing of the unknown-face queue is audit-logged (FR-37).

## Development and Testing

- Development and tests use recorded clips and face sets from people who have explicitly consented to test use, stored outside Git (`standards/12-git-standards.md`).
- Never copy production snapshots or embeddings to a developer machine.
