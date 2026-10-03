# CLAUDE.md — Master Control File
## FaceTrack — Automated Face Recognition Attendance System — AI Coding Framework

**Version:** 2.0 (FaceTrack)
**Stack:** Python 3.12 + FastAPI (backend + recognition engine) · React 18 + TypeScript + Vite (frontend) · PostgreSQL 16 + pgvector (database) · Redis + Celery (events and jobs) · CPU-only (no GPU)
**Requirements source of truth:** `docs/requirements.md` (FaceTrack Requirements & Technical Proposal, v1.2)

This file is the **single controller** for every other instruction file in this project. `standards/*.md` and `commands/*.md` do not stand alone — they only take effect through this file, and this file's protocol governs how they are used. No other document in this project overrides this one. Business behaviour (what the system must do) comes from `docs/requirements.md`; how code is written comes from this file and its standards.

---

## 0. MASTER CONTROL PROTOCOL (read this every time, no exceptions)

This section is not background context — it is a hard operating protocol that runs **before every single task**, every time, even within the same session.

1. **Re-check this file before acting.** At the start of every task — a new request, a follow-up, a "just one more thing" — confirm you are following this protocol. Do not rely on having read it earlier in the conversation.
2. **Identify and read the applicable file(s) before writing or changing anything:**
   - Match the task to the relevant row(s) in the **Standards Index** (§3) and read them.
   - If the task matches a defined workflow in the **Commands Index** (§3a), open that command file and follow its steps exactly, in order.
   - If a task touches multiple areas (e.g. a feature spans engine + backend + frontend), read every relevant standards file first — not just the first one that seems to fit.
   - If the task implements or changes business behaviour, find the matching requirement IDs (FR-x, NFR-x, AC-x) in `docs/requirements.md` and read them.
3. **Do only what is defined in `standards/` and `commands/`.** These two folders are the complete boundary of allowed conventions, patterns, and processes for this project. Do not:
   - Invent a new folder structure, naming convention, response format, or architectural pattern that isn't already in `standards/`.
   - Invent a new multi-step process for a task type that already has a file in `commands/` — follow the existing one instead.
   - Add a new library, pattern, or abstraction "because it's best practice" if it isn't already sanctioned here (the sanctioned stack is listed in §1.2).
4. **If something is not covered by these files, STOP and ask** — do not improvise a reasonable-sounding answer and proceed. Say explicitly: *"This isn't covered in standards/commands — here's what I'd propose, confirm before I proceed."*
5. **Never silently skip, soften, or "improve on" a rule** in `standards/` or `commands/`. If a rule seems to block a legitimate need, say so out loud and ask — do not quietly work around it.
6. **When in doubt, do less, not more.** Stay inside the smallest scope that the standards/commands already permit. Going "outside the box" is a failure mode even if the result looks fine.
7. **This protocol applies to every kind of output** — new code, edits, refactors, reviews, and even suggestions/opinions given in chat. If asked for an opinion or a recommendation, ground it in what these files and `docs/requirements.md` already say rather than general AI training knowledge.
8. **Every time any change is actually made to code, create a batch log file in `batch/` before ending the task.** This is not optional, is not skipped for "small" changes, and is not replaced by only summarizing changes in chat. See §7 (Batch Change Log) for the exact format and naming rule. A task that touched no code (pure discussion, a read-only review with no fixes applied, answering a question) does not need a batch log.

If any instruction from the user directly conflicts with `standards/`, `commands/` or `docs/requirements.md`, point out the conflict explicitly and ask for confirmation before proceeding — do not silently pick a side.

---

## 1. Core Setup

### 1.1 What FaceTrack is

FaceTrack watches existing office CCTV/IP cameras, recognises enrolled employees by face, and marks their attendance automatically. Final attendance is pushed to the HR/payroll system. Everything runs on-premise on ITRC's existing data center servers.

### 1.2 Components and sanctioned stack

| Component | Folder | Technology | Responsibility |
|---|---|---|---|
| Recognition engine | `engine/` | Python 3.12, FastAPI (internal API), PyAV, OpenCV, OpenVINO / ONNX Runtime CPU, FAISS, ByteTrack (`supervision`) | Reads camera streams adaptively, detects/tracks faces, embeds best crops, matches, emits recognition events. **Never decides attendance.** |
| Shared package | `common/` | Python 3.12, SQLAlchemy 2.0, Pydantic v2 | Database models, Pydantic schemas, the recognition-event contract, shared constants. Used by both engine and backend. |
| Backend | `backend/` | Python 3.12, FastAPI, SQLAlchemy 2.0 (async) + asyncpg, Alembic, Celery 5 + Celery Beat, PyJWT, ldap3, XlsxWriter, WeasyPrint | REST API, WebSockets, attendance rules, corrections, reports, auth/RBAC, HR/payroll integration, scheduled jobs. **The only owner of business rules.** |
| Frontend | `frontend/` | React 18, TypeScript (strict), Vite, React Router, TanStack Query + Table, React Hook Form + Zod, Tailwind CSS + shadcn/ui, Recharts, orval (generated API client) | Admin/HR/manager/employee portal (single-page app). Presentation and user interaction only. |
| Data and infrastructure | `infra/` | PostgreSQL 16 + pgvector, Redis 7 (Streams + Pub/Sub), MinIO, MediaMTX, Nginx, Docker Compose, Prometheus + Grafana | Storage, event bus, snapshots, live-view restream, reverse proxy, deployment, monitoring. |

### 1.3 Non-negotiable project constraints

- **CPU only.** There is no GPU. All decoding and inference must run on Intel Xeon CPUs. Engine code must follow `standards/17-recognition-engine-cpu.md` (adaptive camera modes, latest-frame-only buffers, best-crop-only embedding, degradation ladder).
- **A false accept is worse than a miss.** Marking the wrong employee present is the most serious error the system can make. Never loosen thresholds, margins or voting rules to "improve recognition" without explicit approval (NFR-2).
- **Biometric data is protected data.** Follow `standards/18-privacy-and-biometric-data.md`: consent before enrollment, no raw video storage, encryption at rest, retention and erasure.
- **On-premise, no cloud.** No code may send video, images, embeddings or employee data to any external/cloud service.
- **Environments:** Development, staging, and production are configured separately — never share credentials or config between them. Development uses recorded video files, never live production cameras, unless explicitly approved.

---

## 2. Mandatory Rules (apply to every task)

1. Do not unnecessarily change existing functionality.
2. Do not rewrite entire files when a small, targeted change is sufficient.
3. Before modifying code, understand the existing architecture and dependencies.
4. Reuse existing components, utilities, schemas, services, and APIs whenever possible — check `common/` first for anything shared between engine and backend.
5. Do not duplicate existing functionality.
6. Do not introduce a new library when the existing stack (§1.2) can solve the problem.
7. Do not hardcode credentials, secrets, URLs, API keys, passwords, camera RTSP URLs, thresholds, or environment-specific configuration. Configuration comes from `.env` (via pydantic-settings) or the `settings` table.
8. Never expose sensitive information in frontend code.
9. Never directly access PostgreSQL, Redis or MinIO from the React frontend.
10. The frontend communicates with the backend only through the REST API (`/api/v1`) and the `/ws/live` WebSocket.
11. The backend is responsible for business logic and database writes. The engine only produces recognition events and snapshots; it never writes attendance.
12. Backend validation (Pydantic + service-level checks) is mandatory even if frontend validation exists.
13. All new functionality must follow the existing project structure (`standards/01-project-structure.md`).
14. Maintain backward compatibility of the REST API and the recognition-event contract unless the user explicitly requests a breaking change.
15. Do not remove existing functionality unless explicitly requested.
16. Do not silently change business rules (attendance rules, thresholds, retention periods, permissions).
17. If requirements are ambiguous, flag the ambiguity before implementing a potentially destructive change.
18. Prefer simple, maintainable solutions over unnecessarily complex ones.
19. Code must be readable by another developer without AI-specific context.
20. Never claim code works unless it has actually been run/tested.
21. Any change to the recognition engine must state its CPU impact (measured, not guessed) — see `commands/engine-change.md`.
22. Reference the requirement IDs (FR-x, NFR-x) a change implements in commit messages, test names and the batch log.

---

## 3. Standards Index

Read the file relevant to the task before writing code. This list is exhaustive — if a task doesn't map to any row, treat it as "not covered" per §0.4.

| File | Covers |
|---|---|
| `standards/01-project-structure.md` | Monorepo layout: `common/`, `engine/`, `backend/`, `frontend/`, `infra/`, `docs/`, `batch/` |
| `standards/02-backend-architecture.md` | Request flow (Router → Schema → Service → Repository → DB), Celery tasks, event consumer |
| `standards/03-fastapi-coding-standards.md` | Naming, async rules, dependencies, router conventions |
| `standards/04-rest-api-standards.md` | Endpoint conventions, response envelope, status codes, WebSocket messages |
| `standards/05-database-postgresql.md` | SQLAlchemy 2.0 usage, query optimization, Alembic migrations, transactions, pgvector |
| `standards/06-security-and-auth.md` | Secrets, JWT cookies, RBAC, API keys, production security checklist |
| `standards/07-frontend-architecture.md` | React + TypeScript structure, component & naming rules |
| `standards/08-frontend-state-and-api-layer.md` | Generated API client, TanStack Query, WebSocket hook, env vars, state management |
| `standards/09-forms-errors-logging.md` | Form validation, error handling, structured logging |
| `standards/10-python-standards.md` | Python 3.12, Ruff, mypy, type hints, dependency management |
| `standards/11-testing.md` | What to test (engine, backend, frontend), pre-completion checklist |
| `standards/12-git-standards.md` | Commit message conventions, what never to commit (models, recordings, face images) |
| `standards/13-documentation-and-comments.md` | Comment style, README, OpenAPI, requirement references |
| `standards/14-performance-and-file-uploads.md` | Backend/frontend performance, enrollment photo uploads, snapshot storage |
| `standards/15-business-logic-and-duplication.md` | Single source of truth (attendance rules live only in the backend), refactor discipline |
| `standards/16-change-management-and-workflow.md` | Step-by-step workflow, impact analysis, modifying vs adding features |
| `standards/17-recognition-engine-cpu.md` | CPU-only engine design: camera modes, frame handling, models, thread budgets, load shedding |
| `standards/18-privacy-and-biometric-data.md` | Consent, data minimisation, encryption, retention, erasure, audit |

---

## 3a. Commands Index

Defined, repeatable workflows. If a task matches one of these, **use it as-is** — do not design your own process for a task type that's already covered here.

| Command | Use for |
|---|---|
| `commands/new-feature.md` | Adding a feature that spans backend + frontend (and engine, if needed) |
| `commands/add-crud-module.md` | Scaffolding a full CRUD resource (model → migration → API → UI), e.g. shifts, holidays, departments |
| `commands/engine-change.md` | Any change to the recognition engine pipeline, models, thresholds or camera handling |
| `commands/fix-bug.md` | Bug fixes, following the refactoring rule |
| `commands/code-review.md` | Reviewing code/a PR against these standards |

---

## 4. The AI Must NOT

- Rewrite the project unnecessarily.
- Delete working code without permission.
- Change database structure without considering existing data.
- Change API contracts or the recognition-event contract without considering all consumers (frontend, backend, engine, payroll).
- Introduce unnecessary dependencies — in particular, never add a GPU/CUDA dependency or any cloud AI/vision service.
- Hardcode credentials, RTSP URLs or thresholds.
- Disable security protections to make an error disappear.
- Hide errors instead of fixing their root cause.
- Remove tests because they fail.
- Change unrelated files.
- Create duplicate utilities/components.
- Assume requirements that could materially change business behavior.
- Claim successful testing without actually testing.
- Use production credentials or live production cameras during development.
- Store secrets in frontend code.
- Store raw video, or keep face images/embeddings beyond the retention rules.
- Lower match thresholds, margins or voting requirements, or disable liveness, without explicit approval.
- Process every frame of every camera, or add any queue that can grow without bound in the engine.
- Introduce a convention, pattern, folder, library, or process not already defined in `standards/` or `commands/` without flagging it first (§0.4).
- Skip creating the `batch/` log file after making a code change, or substitute a chat-only summary for it (§7).

---

## 5. Code Quality Priority

When decisions conflict, prioritize in this order:

1. Correctness (including recognition correctness: no wrong-person marks)
2. Security and privacy
3. Maintainability
4. Existing architecture consistency
5. Performance (for the engine: CPU efficiency and smooth, backlog-free operation)
6. Simplicity
7. Developer convenience

Never sacrifice correctness, security or privacy for convenience or speed.

---

## 6. Final AI Response Format

After completing a coding task, respond with:

**Changes Made** — short description of what was implemented.

**Requirements** — FR/NFR/AC IDs implemented or affected.

**Files Changed**
```
common/...
engine/...
backend/...
frontend/...
```

**Database Changes** — Alembic migrations, if any.

**CPU / Performance Impact** — required for engine changes (measured before/after); "N/A" otherwise.

**Testing** — state exactly what was tested (and what wasn't).

**Standards/Commands Used** — which files from `standards/`/`commands/` this task followed.

**Batch Log** — path to the batch file created for this change, e.g. `batch/2026-10-05_1430_add-shift-crud.md` (see §7). If no code was changed, state that explicitly instead.

**Notes** — limitations, assumptions, or anything unverified — including anything that fell outside `standards/`/`commands/` and was flagged per §0.4.

Keep the response concise.

---

## 7. Batch Change Log (Mandatory)

Every time code is actually created, edited, or removed — for any task, whether it came from `commands/new-feature.md`, `commands/add-crud-module.md`, `commands/engine-change.md`, `commands/fix-bug.md`, a fix applied during `commands/code-review.md`, or any ad-hoc request — create **one new markdown file** in the `batch/` folder at the project root as the last step, right before giving the Final AI Response.

Do not skip this for small changes. Do not edit or overwrite a previous batch file to fold in new work — each unit of work gets its own new file, so `batch/` reads as a chronological, append-only change log.

### Where

```
project-root/
└── batch/
    ├── 2026-10-05_1430_add-shift-crud.md
    ├── 2026-10-05_1615_fix-night-shift-day-close.md
    └── 2026-10-06_0930_add-keyframe-idle-mode.md
```

If `batch/` doesn't exist yet, create it.

### Naming / Labeling

```
batch/YYYY-MM-DD_HHMM_short-kebab-case-label.md
```

- `YYYY-MM-DD_HHMM` — date and 24-hour time the batch was created (use the actual current date/time, Asia/Karachi).
- `short-kebab-case-label` — a short, descriptive label for the change (3–6 words, lowercase, hyphen-separated), e.g. `add-shift-crud`, `fix-night-shift-day-close`, `add-keyframe-idle-mode`. Pick one that would let someone recognize the change from the filename alone.
- Never reuse a label/filename for a different change. Never overwrite an existing batch file.

### Required Content

```markdown
# Batch: <short-kebab-case-label>

**Date:** YYYY-MM-DD HH:MM
**Type:** feature | bugfix | crud-module | engine-change | refactor | review-fix | other
**Command Used:** commands/<file>.md (or "ad-hoc" if none applied)
**Standards Referenced:** standards/<file>.md, standards/<file>.md
**Requirements:** FR-x, NFR-x (or "none")

## Summary
One or two sentences: what changed and why.

## Changes Made
- Bullet list of the actual changes (mirrors "Changes Made" in the Final AI Response).

## Files Changed
```
backend/...
frontend/...
```

## Database Changes
Alembic migrations created/run, if any. State "None" if not applicable.

## CPU / Performance Impact
Measured before/after for engine changes (CPU %, per-step ms, cameras per node). "N/A" otherwise.

## Testing
Exactly what was tested, and what was not.

## Notes
Assumptions, limitations, or anything flagged per §0.4 as outside `standards/`/`commands/`.
```

This file is the persistent record — the Final AI Response in chat is a summary for the user in the moment, `batch/*.md` is the durable log for the project.

---

## 8. Golden Rule

> Understand first. Reuse existing code. Make the smallest safe change. Keep business rules in the backend and only there. Keep the engine lean, CPU-aware and backlog-free. Keep the frontend responsible for presentation and user interaction. Never mark the wrong person. Protect biometric data, the database and secrets. Stay inside `standards/` and `commands/` — flag anything that isn't. Log every code change in `batch/`. Test before declaring completion.

This document is the default coding standard for FaceTrack and the controlling entry point for `standards/` and `commands/`, unless a project-specific instruction explicitly overrides it.
