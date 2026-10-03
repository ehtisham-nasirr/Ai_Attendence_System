# CLAUDE.md — FaceTrack (project root)

@Guardrails/CLAUDE.md

## Where things are

- **How code is written:** `Guardrails/CLAUDE.md` (imported above) is the master control file. Its `standards/` and `commands/` paths resolve under `Guardrails/` (`Guardrails/standards/*.md`, `Guardrails/commands/*.md`).
- **What to build:** `docs/requirements.md` — FaceTrack Requirements & Technical Proposal v1.2 (converted unchanged from `Requirements.docx`). It is the source of truth for business behaviour and requirement IDs (FR-x, NFR-x, AC-x).
- **Change log:** `batch/` lives at the **repository root** (not under `Guardrails/`). Every code change adds one new file there, per `Guardrails/CLAUDE.md` §7.
- **Decisions and open items:** `docs/open-questions.md` (unclear points and the option chosen) and `docs/adr/` (decisions that change the stack or a core rule).

Read `Guardrails/CLAUDE.md` §0 before every task, then the matching standards/commands files and requirement IDs.
