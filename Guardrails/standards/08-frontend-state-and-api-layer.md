# API Client, Environment Variables & State Management

## Generated API Client

The backend's OpenAPI spec is the contract. The frontend client is **generated** from it with orval into `src/api/generated/` — never hand-write request functions or response types for endpoints that exist in the spec.

```bash
make gen-api        # fetches /api/openapi.json and regenerates src/api/generated
```

- After any backend schema change, regenerate the client in the same change.
- `src/api/client.ts` holds the single axios instance: base URL, `withCredentials: true` (JWT cookie), CSRF header, response interceptor that unwraps the `{ success, message, data }` envelope, and 401 handling (redirect to login).

```ts
// hooks/useEmployees.ts — components use hooks, hooks use the generated client
export function useEmployees(filters: EmployeeFilters) {
  return useQuery({
    queryKey: ["employees", filters],
    queryFn: () => listEmployees(filters),
  });
}
```

Components never import axios or build URLs.

## Server State — TanStack Query

- All data from the API is server state and lives in TanStack Query, not in `useState` or a global store.
- Query keys are arrays starting with the resource name (`["attendance", { date, departmentId }]`).
- Mutations invalidate the affected query keys on success.
- Live updates from the WebSocket update or invalidate the matching query cache — they do not keep a separate copy of the data.

## Live Feed — WebSocket

- One shared hook, `useLiveFeed()`, owns the `/ws/live` connection (auto-reconnect with backoff, pause when the tab is hidden).
- It dispatches messages by `type` (see `standards/04-rest-api-standards.md`) into the TanStack Query cache.
- Pages must not open their own WebSocket connections.

## Live Video

Live camera view uses the WebRTC/HLS URL returned by `GET /api/v1/cameras/{id}/live` (MediaMTX). Never connect to camera RTSP URLs or credentials from the browser.

## Environment Variables

```env
VITE_API_BASE_URL=/api/v1
VITE_WS_URL=/ws/live
```

- Use relative URLs in production (Nginx serves the SPA and proxies `/api` and `/ws`), so builds are environment-independent.
- Anything prefixed `VITE_` is shipped to the browser and is **public** — never put secrets there.

## Client State

Use the simplest approach, in this order:

1. Local component state (`useState`/`useReducer`)
2. URL state (filters, pagination, selected date) via search params, so views are shareable
3. React Context for small app-wide UI state (theme, selected location, current user)
4. A global store (e.g. Zustand) — **not adopted**; flag before introducing one (CLAUDE.md §0.4)
