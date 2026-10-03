# Project Structure

FaceTrack is a **monorepo** with one shared Python package and three applications. If the repository already uses a different structure, **do not restructure it automatically** — follow the existing layout unless restructuring is explicitly requested.

## Layout

```
facetrack/
│
├── common/                          ← shared Python package (installed into engine and backend)
│   ├── pyproject.toml
│   └── facetrack_common/
│       ├── models/                  ← SQLAlchemy 2.0 models (one module per table group)
│       ├── schemas/                 ← Pydantic v2 schemas shared by engine + backend
│       ├── events.py                ← recognition-event contract (the ONLY definition)
│       ├── constants.py             ← camera roles, attendance statuses, enums
│       └── settings_keys.py         ← names of keys in the `settings` table
│
├── engine/                          ← recognition engine (CPU only) — see standards/17
│   ├── pyproject.toml
│   ├── .env.example
│   ├── app/
│   │   ├── api/                     ← internal FastAPI routes: embed, gallery, cameras, load, health
│   │   ├── capture/                 ← PyAV decoders, keyframe-only mode, reconnect, watchdog
│   │   ├── scheduler/               ← camera modes, priority, degradation ladder, load monitor
│   │   ├── models/                  ← Detector / Embedder / LivenessChecker interfaces + OpenVINO/ONNX impls
│   │   ├── pipeline/                ← motion gate, quality, tracking, best-crop selection, voting, matching
│   │   ├── gallery/                 ← FAISS index, reload from DB
│   │   ├── publisher/               ← Redis stream publisher + local disk buffer
│   │   └── config.py                ← pydantic-settings
│   ├── scripts/                     ← download_models.py, convert_int8.py, evaluate.py, benchmark_cpu.py
│   ├── tests/
│   └── Dockerfile
│
├── backend/                         ← FastAPI app (REST API + WebSockets + Celery)
│   ├── pyproject.toml
│   ├── .env.example
│   ├── app/
│   │   ├── main.py                  ← app factory, router registration, middleware
│   │   ├── api/v1/                  ← routers: auth, employees, cameras, attendance, corrections,
│   │   │                              unknown_faces, events, reports, settings, audit_logs, integration
│   │   ├── schemas/                 ← API request/response schemas (backend-only; shared ones live in common/)
│   │   ├── domain/                  ← business logic per area (services): attendance/, corrections/,
│   │   │                              employees/, recognition/, reports/
│   │   ├── repositories/            ← database access (SQLAlchemy queries) per aggregate
│   │   ├── services/                ← infrastructure services: hr_sync, payroll_push, email, storage, engine_client
│   │   ├── worker/                  ← Celery app + tasks: process_event, close_day, sync_hr, push_payroll, retention
│   │   ├── ws/                      ← WebSocket live feed (Redis Pub/Sub fan-out)
│   │   └── core/                    ← config, security (JWT, RBAC deps), db session, responses, exceptions, pagination
│   ├── alembic/
│   │   └── versions/
│   ├── tests/
│   └── Dockerfile
│
├── frontend/                        ← React 18 + TypeScript + Vite SPA
│   ├── package.json
│   ├── .env.example
│   ├── orval.config.ts              ← API client generation from the backend OpenAPI spec
│   ├── src/
│   │   ├── api/                     ← generated client (do not hand-edit) + axios instance
│   │   ├── components/              ← ui/ (shadcn), plus feature folders: employees/, cameras/, attendance/ ...
│   │   ├── hooks/                   ← TanStack Query hooks, useLiveFeed (WebSocket), useAuth
│   │   ├── layouts/                 ← AppLayout (sidebar + top bar), AuthLayout
│   │   ├── pages/                   ← one folder per screen (see requirements §13)
│   │   ├── routes/                  ← React Router config + route guards
│   │   ├── lib/                     ← utils, formatters, zod schemas
│   │   ├── types/                   ← app-level types not covered by the generated client
│   │   ├── App.tsx
│   │   └── main.tsx
│   └── public/
│
├── infra/
│   ├── docker-compose.yml           ← backend stack
│   ├── docker-compose.engine.yml    ← engine node (one per server)
│   ├── nginx/
│   ├── mediamtx/
│   └── monitoring/                  ← prometheus.yml, grafana dashboards, alert rules
│
├── docs/
│   ├── requirements.md              ← source of truth for business behaviour
│   ├── open-questions.md
│   ├── adr/                         ← architecture decision records
│   └── runbook.md
├── batch/                           ← append-only AI change log (CLAUDE.md §7)
├── .gitignore
├── Makefile                         ← make dev, make test, make lint, make gen-api
└── README.md
```

## Placement Rules

- **Anything used by both engine and backend goes in `common/`** — never copy a model, schema, enum or the event contract into both apps.
- **Business rules live in `backend/app/domain/`** — not in routers, repositories, Celery tasks, the engine, or the frontend.
- **Database queries live in `backend/app/repositories/`** — domain services call repositories; routers never build queries.
- **The engine has no knowledge of attendance** — no shift, leave or status logic in `engine/`.
- **Generated code is never hand-edited** — `frontend/src/api/generated/` is regenerated with `make gen-api`.

## Next.js

Not used. The portal is an internal SPA built with Vite. Do not add Next.js, server components or SSR.
