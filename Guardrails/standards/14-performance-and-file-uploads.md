# Performance & File Uploads

Engine (video and inference) performance rules are in `standards/17-recognition-engine-cpu.md`. This file covers the backend and frontend.

## Performance

Do not optimize prematurely — but avoid these obvious problems:

- N+1 database queries (see `standards/05-database-postgresql.md`)
- Unpaginated list endpoints, especially on `recognition_events` and `attendance_days`
- Heavy work inside requests — reports, PDF/Excel exports and bulk imports run in Celery and return `202`
- Unnecessary/duplicate API calls (use TanStack Query caching; don't refetch on every render)
- Polling where the WebSocket already pushes updates
- Rendering huge lists without pagination or virtualization (monthly register grid, event log)
- Loading full-size snapshots in tables — use thumbnails
- Excessive re-renders from the live feed (batch WebSocket updates; don't re-render the whole dashboard per event)

Remember the backend shares data center servers with engine nodes in small deployments: keep Celery concurrency and Gunicorn worker counts configurable so they don't starve the engine of CPU.

## File Uploads

Uploads in FaceTrack are enrollment photos (single images and ZIP bulk import) and Excel/CSV employee imports. For any uploaded file:

- Validate file type by content (magic bytes / Pillow open), not just the extension. Allowed: JPEG, PNG for photos; ZIP for bulk photos; XLSX/CSV for imports.
- Validate size (photo ≤ 5 MB, ZIP ≤ 200 MB, import ≤ 10 MB) — configurable.
- For ZIPs, reject path traversal, nested archives and excessive file counts.
- Strip EXIF metadata from photos before storage.
- Run enrollment validation through the engine `/embed` endpoint (exactly one face, face width ≥ 112 px, quality, blur — FR-9) and return clear rejection reasons.
- Generate a safe, non-guessable object name server-side; never use the client filename.
- Store files only in MinIO through `services/storage.py` — never on ad-hoc local paths.
- Never execute uploaded files; never render user-uploaded content as HTML.
- Enrollment is blocked unless the employee's consent is recorded (`standards/18-privacy-and-biometric-data.md`).
