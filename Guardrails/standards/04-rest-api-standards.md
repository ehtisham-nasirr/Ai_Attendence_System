# REST API Standards

All public endpoints live under `/api/v1`. The internal engine API (`engine:/embed`, `/gallery/reload`, `/cameras/*`, `/load`, `/health`) is reachable only from the backend network and follows the same envelope.

## Endpoint Conventions

Use consistent, resource-based endpoints with **plural** nouns and **no trailing slash**:

```
GET    /api/v1/employees
GET    /api/v1/employees/{id}
POST   /api/v1/employees
PUT    /api/v1/employees/{id}
PATCH  /api/v1/employees/{id}
DELETE /api/v1/employees/{id}
GET    /api/v1/employees/{id}/faces          ← sub-resource
```

**Avoid** verb-based/RPC-style URLs:

```
/api/v1/getEmployees
/api/v1/createCamera
/api/v1/deleteFace
```

**State transitions** that are not plain CRUD are modelled as a `POST` on a named action sub-resource — and only these, as defined in requirements §12:

```
POST /api/v1/corrections/{id}/approve
POST /api/v1/corrections/{id}/reject
POST /api/v1/unknown-faces/{id}/assign
POST /api/v1/events/{id}/void
POST /api/v1/cameras/{id}/test
```

Use kebab-case for multi-word path segments (`/unknown-faces`, `/audit-logs`) and `snake_case` for JSON fields and query parameters (`work_date`, `page_size`).

## Response Shape

Use one consistent envelope across the whole API. Helpers live in `backend/app/core/responses.py` (`ok()`, `created()`, `paginated()`, `error()`) — reuse them, do not hand-build response dicts per router.

**Successful response (single object):**
```json
{
  "success": true,
  "message": "Employee retrieved successfully.",
  "data": {}
}
```

**List response (with pagination):**
```json
{
  "success": true,
  "message": "Employees retrieved successfully.",
  "data": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100
  }
}
```

**Error response:**
```json
{
  "success": false,
  "message": "Unable to process request.",
  "errors": {}
}
```

FastAPI's default validation error (`{"detail": [...]}`) MUST be converted to this envelope by the global exception handler in `core/exceptions.py`, with `errors` keyed by field name.

The integration endpoint for payroll (`GET /api/v1/integration/attendance?date=YYYY-MM-DD`) uses the same envelope.

## HTTP Status Codes

| Code | Meaning | Use for |
|---|---|---|
| 200 | OK | Successful GET/PUT/PATCH, and action endpoints that return a body |
| 201 | Created | Successful POST that creates a resource |
| 202 | Accepted | Work handed to a background job (e.g. bulk import, report export) |
| 204 | No Content | Successful DELETE with no body |
| 400 | Bad Request | Malformed request |
| 401 | Unauthorized | Missing/invalid/expired authentication |
| 403 | Forbidden | Authenticated but not permitted (role or department scope) |
| 404 | Not Found | Resource doesn't exist or is outside the user's scope |
| 409 | Conflict | State conflict (duplicate employee code, correction already decided) |
| 422 | Unprocessable Entity | Validation failed on well-formed input (including rejected enrollment photos) |
| 429 | Too Many Requests | Rate limit exceeded (login, API keys) |
| 500 | Internal Server Error | Unhandled server error |
| 503 | Service Unavailable | Engine unreachable for `/embed` or camera test |

Do not return `200 OK` for every situation — pick the code that actually describes what happened.

## Pagination, Filtering, Sorting

- Query parameters: `page`, `page_size` (default 20, max 200), `sort` (e.g. `sort=-check_in_at`), and resource filters (`department_id`, `status`, `date_from`, `date_to`).
- Every list endpoint is paginated. Exports (Excel/PDF) are separate endpoints or `?format=xlsx|pdf`, not unpaginated list calls.

## Times and IDs

- All timestamps in requests and responses are ISO 8601 in **UTC** with `Z` (e.g. `2026-10-03T04:02:11Z`). The frontend converts to Asia/Karachi for display.
- Business dates (`work_date`) are plain `YYYY-MM-DD` in the location's timezone.

## WebSocket Messages (`/ws/live`)

Messages are JSON with a fixed shape:

```json
{ "type": "RecognitionCreated", "data": { } , "sent_at": "2026-10-03T04:02:12Z" }
```

Allowed `type` values: `RecognitionCreated`, `AttendanceUpdated`, `CameraStatusChanged`, `LoadLevelChanged`. Adding a new type is an API contract change — flag it first.

## Versioning

Breaking changes require a new version prefix or explicit approval (CLAUDE.md §2.14). Adding optional fields is non-breaking; removing or renaming fields is breaking.
