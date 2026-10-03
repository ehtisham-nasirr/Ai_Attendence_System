# Form Validation, Error Handling & Logging

## Form Validation

- **Frontend:** React Hook Form + Zod schemas (`lib/schemas/`) for fast feedback.
- **Backend:** Pydantic schemas + domain-service checks are the actual enforcement.

Never trust frontend validation as the source of truth — always re-validate in the backend, even if the same rule exists in the Zod schema. Where both exist, the error messages should match so users see consistent text.

Map backend `422` field errors (the `errors` object in the envelope) back onto form fields with `setError`.

## Error Handling — Backend

- Raise domain exceptions (`NotFound`, `PermissionDenied`, `Conflict`, `ValidationFailed`, `EngineUnavailable`) from services; the global handlers in `core/exceptions.py` convert them to the standard error envelope and status code.
- Never return raw exception text or stack traces to clients.

## Error Handling — Frontend

Frontend should:

- Display useful, user-facing messages (from the envelope's `message`), not raw errors.
- Handle loading, empty and error states on every page.
- Handle expired authentication (401 → redirect to login, keep the return URL).
- Show a clear message when the engine is unavailable (503) during enrollment or camera test.

Do not silently swallow errors:

```ts
// Avoid
try {
  await approveCorrection(id);
} catch {}

// Prefer
try {
  await approveCorrection(id);
} catch (error) {
  reportError(error);               // project logger
  toast.error(getErrorMessage(error));
}
```

## Error Handling — Engine

- A failure in one camera's decoder or a single frame must never stop other cameras. Catch, log with the camera ID, and let the watchdog restart the decoder (`standards/17-recognition-engine-cpu.md`).
- Never swallow exceptions in the inference pool silently — count them as a metric and log at `ERROR`.

## Logging

All Python services log **structured JSON** to stdout (collected centrally), using the standard `logging` module with the project's JSON formatter. Every log line includes the service name and, where relevant, `camera_id`, `event_uuid`, `employee_id` or `request_id`.

| Level | Use for |
|---|---|
| `DEBUG` | Detailed diagnostic info, dev only |
| `INFO` | Normal operational events (camera mode change, day closed, payroll pushed) |
| `WARNING` | Unexpected but recoverable (stream reconnect, degradation step down, retry) |
| `ERROR` | A failure that needs attention (decoder crash, failed payroll push) |
| `CRITICAL` | System-level failure (database unreachable, engine node down) |

**Never log:**

- Passwords, JWTs, API keys, camera credentials or full RTSP URLs with credentials
- Embedding vectors or face images
- Personal data beyond the employee ID/code needed for tracing

Never log per-frame events at `INFO` — the engine would flood the logs. Use metrics (Prometheus counters/histograms) for per-frame and per-camera numbers.
