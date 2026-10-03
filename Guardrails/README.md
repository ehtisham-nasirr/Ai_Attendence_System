# AI Coding Instructions — FaceTrack (FastAPI + React + PostgreSQL, CPU-only)

This folder is the coding guardrail set for an AI coding assistant working on **FaceTrack**, ITRC's automated face recognition attendance system:

- **Recognition engine:** Python 3.12 + FastAPI (internal), PyAV, OpenCV, OpenVINO / ONNX Runtime **on CPU only**
- **Backend:** Python 3.12 + FastAPI, SQLAlchemy 2.0, Alembic, Celery
- **Frontend:** React 18 + TypeScript + Vite, TanStack Query, shadcn/ui
- **Database:** PostgreSQL 16 + pgvector · **Messaging:** Redis Streams / Pub/Sub · **Files:** MinIO

It's the same idea as a project's `CLAUDE.md`/`.cursorrules`/`.windsurfrules` setup — one master file plus focused topic files the assistant reads before touching code. Business requirements live in `docs/requirements.md` (the FaceTrack Requirements & Technical Proposal); these files govern *how* the code is written.

## What's Inside

```
Guardrails/
├── CLAUDE.md                              ← master file: read this first
├── README.md                              ← this file
├── batch/                                 ← auto-generated change log (see batch/README.md)
│   ├── README.md
│   └── 0000-example.md                    ← delete once you've seen the format
├── commands/
│   ├── new-feature.md
│   ├── add-crud-module.md
│   ├── engine-change.md                   ← FaceTrack-specific: any recognition engine change
│   ├── fix-bug.md
│   └── code-review.md
└── standards/
    ├── 01-project-structure.md
    ├── 02-backend-architecture.md
    ├── 03-fastapi-coding-standards.md
    ├── 04-rest-api-standards.md
    ├── 05-database-postgresql.md
    ├── 06-security-and-auth.md
    ├── 07-frontend-architecture.md
    ├── 08-frontend-state-and-api-layer.md
    ├── 09-forms-errors-logging.md
    ├── 10-python-standards.md
    ├── 11-testing.md
    ├── 12-git-standards.md
    ├── 13-documentation-and-comments.md
    ├── 14-performance-and-file-uploads.md
    ├── 15-business-logic-and-duplication.md
    ├── 16-change-management-and-workflow.md
    ├── 17-recognition-engine-cpu.md       ← FaceTrack-specific: CPU-only engine rules
    └── 18-privacy-and-biometric-data.md   ← FaceTrack-specific: biometric data rules
```

## How to Use It

Drop this whole folder into the root of the `facetrack/` repository. Depending on which AI tool you use:

- **Claude Code:** move this folder's contents into `.claude/` at the project root (`CLAUDE.md` stays at the project root either way — Claude Code reads it automatically).
- **Cursor:** point `.cursorrules` (or `.cursor/rules/`) at `CLAUDE.md`, or copy its contents in.
- **Any other AI coding tool / manual use:** keep the folder as-is and tell the assistant to read `CLAUDE.md` first, then the relevant `standards/*.md` file for whatever it's working on.

Also place the requirements document at `docs/requirements.md` (export the FaceTrack proposal to Markdown) — `CLAUDE.md` treats it as the source of truth for business behaviour and requirement IDs.

## What Changed From the Generic Version

The original set targeted Django + DRF + MySQL with React or Next.js. For FaceTrack it now targets:

| Area | Before | Now |
|---|---|---|
| Backend | Django + DRF | FastAPI + SQLAlchemy 2.0 + Alembic + Celery |
| Database | MySQL | PostgreSQL 16 + pgvector |
| Frontend | React or Next.js, JavaScript | React 18 + TypeScript + Vite only (no Next.js) |
| API client | Hand-written services | Generated from OpenAPI (orval) + TanStack Query |
| New areas | — | Recognition engine on CPU (`17`), biometric privacy (`18`), `commands/engine-change.md` |

## The `batch/` Change Log

`CLAUDE.md` §7 requires the AI to create one new markdown file in `batch/` after every real code change — labeled `YYYY-MM-DD_HHMM_short-label.md`, containing a summary of what changed, requirement IDs, files touched, migrations, CPU impact (for engine changes), and testing. It never edits old batch files, only adds new ones — so `batch/` ends up as a readable, chronological history of everything the AI did on this project. Delete `batch/0000-example.md` once you've seen the format.

## Customizing

This is a starting point, not a law. If the project settles on different conventions, update these files to match — the whole point is that the AI assistant follows *FaceTrack's* real conventions, not a generic default it has to guess at.
