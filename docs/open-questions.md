# Open questions and decisions taken

Per requirements §20 rule 7, anything unclear is listed here with the option chosen (the safest one: no wrong-person mark, no data exposure). Items marked **Decided by owner** were confirmed on 2026-10-03. Everything else is an implementation default that the owner should confirm; each is configurable unless stated.

Owner questions from requirements §21 (camera inventory, employee count, HR/payroll system, shift patterns, exit routes, model licence, servers, sub-streams, AD, retention approval, notification channel, go-live) remain open — they need the Phase 0 site survey.

## Pending owner input (needed before production; work continued with the safe default)

| # | Needs from the owner | Default used meanwhile |
|---|---|---|
| P1 | Model and licence decision (§9): buy an InsightFace commercial licence for ArcFace, or accept SFace. Needs the Phase 1 evaluation on consented ITRC data. | SFace (permissive). ArcFace implemented but unused. |
| P2 | Production object store (ADR-0005): the open-source MinIO server is archived (no security updates; images/binaries withdrawn). Choose a shared volume/NFS or a maintained S3-compatible server. | Encrypted local volume shared by engine and backend. S3 backend ready. |
| P3 | Liveness model: approve converting the official Silent-Face-Anti-Spoofing (Apache-2.0) weights to ONNX, and the spoof threshold (Q5). | Liveness off; cameras with liveness enabled refuse to start without a model. |
| P4 | Consented evaluation data (gallery + labelled passes) and a reference server to run `scripts/evaluate.py` (TAR/FAR) and `scripts/benchmark_cpu.py`. | Accuracy unverified; CPU numbers are from the dev container only. |
| P5 | Real camera/RTSP access, sub-stream support and GOP settings (Phase 0 site survey). | Synthetic clips only. |
| P6 | HR/payroll API details (system, push or pull, field mapping, auth) for FR-12/FR-24/FR-35, and Active Directory details for FR-40. | Generic JSON adapters (Q32); LDAP tested against an in-memory mock only. |
| P7 | SMTP server and Teams webhook for notifications (FR-32/FR-33, §18 alerts). | Disabled until configured. |
| P8 | Confirm thresholds invented for unspecified gates: enrollment `min_quality` 0.5 / `min_blur_variance` 60, crop gate `min_crop_quality` 0.35 / `min_blur_variance` 40, daily summary time 10:45. | As listed; all in Settings. |
| P9 | ByteTrack: `supervision` deprecated it (removed in 0.31). Approve moving to Roboflow's `trackers` package or an in-house IoU tracker before upgrading. | `supervision` pinned `<0.31`. |

## Decided by owner (2026-10-03)

| # | Topic | Conflict / gap | Decision | Record |
|---|---|---|---|---|
| D1 | List response envelope | standards/04 `pagination{page,page_size,total}` vs requirements §12.1 `data, meta, links` | Use the standards/04 envelope everywhere. §12.1 wording is superseded. | ADR-0002 |
| D2 | Embedding storage | standards/05 + 18 (AES-256 via the project encryption helper) vs §11 (`vector(512)` + HNSW index) | Embeddings are stored as AES-256-GCM ciphertext (`bytea`) with `model_name` and `embedding_dim`. No HNSW index. Back-office similarity search (FR-10, unknown-face grouping) runs in memory. pgvector extension stays enabled. | ADR-0001 |
| D3 | Daily status when several apply (FR-22) | Not specified | Missing Check-out > Half Day > Late > Early Exit > Present. Late/early/worked/overtime minutes are always stored separately. Manual correction > Leave > Holiday/Weekly Off > automatic (§10.3) still applies on top. | ADR-0003 |
| D4 | Who approves an employee's correction request (FR-26, §21) | Not specified | Any one authorised approver: the employee's department manager, HR Admin or Super Admin (§4). Corrections entered by HR/managers/admins themselves (FR-25) take effect immediately with the reason and original values kept. | ADR-0004 |

## Implementation defaults (choose-safest, please confirm)

| # | Topic | Gap | Choice made |
|---|---|---|---|
| Q1 | Default processing FPS | FR-6 says default 5 FPS; §10.1, §10.4 (ladder step 1) and standards/17 say 4 FPS entrance / 1 FPS general | Role-based defaults 4 / 1 FPS (lower CPU, matches the degradation ladder). `cameras.fps` overrides per camera. |
| Q2 | SFace margin | §9 gives margin 0.08 only for ArcFace | Margin 0.08 for SFace too. Must be tuned in Phase 1 on real data. |
| Q3 | Default embedder | ArcFace weights need an InsightFace commercial licence (§9) | Default config is YuNet + SFace (permissive). ArcFace is implemented behind the same `Embedder` interface but not enabled and not tested with real weights. |
| Q4 | Liveness model files | No official ONNX for MiniFASNet; only community conversions on model hubs | Not downloaded. `scripts/download_models.py` lists the official Silent-Face-Anti-Spoofing (Apache-2.0) source; the ONNX must be converted and its SHA-256 pinned in config. Until then, liveness is disabled per camera and the engine refuses to start a camera that has liveness enabled but no model. |
| Q5 | Liveness threshold | "reject if spoof score > threshold" — no default given | `recognition.liveness_spoof_threshold` = 0.5 (spoof score = 1 − P(real)). To be tuned in Phase 1. |
| Q6 | Liveness-rejected track | Not specified what is stored | Emitted as an **Unknown** event with its `liveness_score`, so the snapshot is reviewable; never as recognized. |
| Q7 | Track with fewer than 3 good crops | FR-15 requires voting over ≥ 3 frames | A track is only confirmed after 3 embedded crops; otherwise it is logged as Unknown when it ends. At most 3 embeddings per track (+1 for an unembedded unknown track's best crop). |
| Q8 | Unknown-face embedding transport | §10.2 payload has no embedding, but §11 `unknown_faces.embedding` needs one | Additive optional field `embedding_encrypted` (AES-256-GCM, base64) in the event contract, plus `model_name` and an optional normalised `bbox` (used for the live-view overlay). |
| Q9 | Snapshot encryption at rest | standards/18 requires it; MinIO SSE needs KMS | Snapshots and enrollment photos are encrypted with the project encryption helper before upload; the backend decrypts when serving them through authenticated endpoints. |
| Q10 | Work-date boundaries / day close | §10.3 says "shift end + 4 h (default 02:00 for day shifts)", which do not agree for a 09:00–18:00 shift | Day shifts: the work day closes at `attendance.day_close_time` (default 02:00 next day). Night shifts: close = shift end + `attendance.night_shift_close_offset_min` (default 240). An event belongs to work date D when close(D−1) < t ≤ close(D). |
| Q11 | Overtime amount | "Worked hours beyond shift end + 30 min" | Literal reading: overtime = check-out − (shift end + threshold) when positive (threshold default 30 min, on/off setting). |
| Q12 | Provisional status before day close | Not specified | Before close only Present/Late are shown (from check-in). Half Day, Early Exit, Missing Check-out and Absent are set by the day-close job (FR-23). |
| Q13 | Employee seen only on an exit camera | §17 edge case, no rule given | No check-in is recorded; at close the status is Present (they were recognised) with check-in empty, so HR can see and correct it. |
| Q14 | Single sighting on an ENTRY_EXIT camera | Not specified | Check-out is only set by a later event than check-in, so one sighting gives Missing Check-out. |
| Q15 | Holiday / weekly off with attendance | Precedence says Holiday > automatic | Status stays Holiday/Weekly Off; check-in/out and worked/overtime minutes are still recorded. Weekly Off ranks with Holiday. |
| Q16 | Leave approval state | `leaves` has no status column | Every leave row is treated as approved leave (imported from HR or entered by HR). |
| Q17 | Account lockout duration | "lock after 5 failed logins", no duration | Locked for `auth.lockout_minutes` (default 30). Super Admin can unlock by resetting the user. |
| Q18 | Password policy | Not specified | Minimum 10 characters, at least one letter and one digit. |
| Q19 | Login identifier | §13 says username; `users` has only email | Added `users.username` (unique). AD login maps `sAMAccountName` to `username`; AD users must already exist in FaceTrack (no auto-provisioning). |
| Q20 | Extra columns | Needed by security/workflow rules | `users.failed_login_attempts`, `users.locked_until`, `users.username`; `attendance_corrections.review_comment`; `face_enrollments.embedding_dim`; `unknown_faces.model_name`. |
| Q21 | Foreign keys to `recognition_events` | Table is range-partitioned by month (§11); PostgreSQL needs the partition key in referenced keys | `attendance_days.check_in_event_id/check_out_event_id` and `unknown_faces.recognition_event_id` are indexed `bigint` columns without FK constraints. `event_uuid` uniqueness is `(event_uuid, captured_at)`; a replayed event carries the same `captured_at`, so duplicates are still rejected. |
| Q22 | Manual attendance entry when no day row exists | FR-25 "add or edit" | `POST /api/v1/attendance` creates a manual day (with reason) for HR/managers; edits go through `POST /attendance/{id}/corrections`. |
| Q23 | Dismissing an unknown face | §13 has "Dismiss", §12 has no endpoint | `PATCH /api/v1/unknown-faces/{id}` with `review_status=dismissed` (plain update, no new action URL). |
| Q24 | Camera connection test | FR-2 needs RTSP decoding, which only the engine has | Internal engine endpoint `POST /cameras/test` (not in §12.2) used by `POST /api/v1/cameras/{id}/test`. |
| Q25 | Live view authorisation | MediaMTX must not be open | `GET /cameras/{id}/live` returns a short-lived signed token; MediaMTX checks it via the backend's internal `/internal/mediamtx/auth` endpoint (not exposed by Nginx). |
| Q26 | Libraries not named in CLAUDE.md §1.2 | Needed as clients/glue for sanctioned components | `cryptography` (AES-256-GCM helper), `redis` (Redis client), `minio` (S3 client for the S3 storage backend, ADR-0005), `psutil` (CPU load monitor), `prometheus-client` (metrics), `numpy`, `httpx`, `argon2-cffi`, `python-multipart` (FastAPI uploads), `Pillow` (upload validation, EXIF strip), `openpyxl` (reading Excel imports; XlsxWriter cannot read), `Jinja2` (WeasyPrint HTML templates), `asyncpg`, `sonner` (shadcn/ui toast), `axios`. No GPU or cloud packages. |
| Q27 | Unknown-face "Add to gallery" quality | FR-27 | The snapshot is re-validated by the engine `/embed` endpoint (same FR-9 rules) before it is added; small crops are rejected with the reason. |
| Q28 | Report exports | standards/14: heavy exports run in Celery and return 202 | `GET /reports/{type}?format=xlsx|pdf` returns 202 with a job id; `GET /report-exports/{job_id}` gives status and `GET /report-exports/{job_id}/file` downloads (only for the requesting user, 24 h). |
| Q29 | Monitoring containers | §18 lists Prometheus + Grafana only | Added `alertmanager` (email + Teams routing for §18 alerts), `node-exporter` (disk > 80% alert) and a `backup` job container (encrypted nightly `pg_dump`, §15). |
| Q30 | Leave entry without HR integration | No screen in §13 | HR can add/remove leave on the employee profile (`/api/v1/leaves`). |
| Q31 | Status letters for the register | §13 lists P, L, A, H, WO, LV, MC only | Added `EE` (Early Exit) and `HD` (Half Day). |
| Q32 | HR / payroll API shape | HR/payroll system unknown (§21) | Generic JSON-over-HTTPS adapters behind `HrClient` / payroll push; field mapping documented in `backend/README.md`. Not verified against a real system. |
