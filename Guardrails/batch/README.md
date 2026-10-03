# batch/

This folder is a **chronological, append-only change log**, maintained automatically by the AI assistant per `CLAUDE.md` §7.

Every time the assistant makes a real code change (new feature, bug fix, CRUD module, engine change, a fix applied during a review, etc.), it creates **one new file here** summarizing that change — it never edits an old batch file to add new work.

## Filename Format

```
YYYY-MM-DD_HHMM_short-kebab-case-label.md
```

Example: `2026-10-05_1430_add-shift-crud.md`

## What's Inside Each File

- Date/time, type of change, which `commands/`/`standards/` file(s) were followed
- Requirement IDs (FR/NFR/AC) implemented or affected
- Summary of the change
- Files changed
- Alembic migration changes
- CPU / performance impact (measured before/after for engine changes)
- What was tested
- Notes / assumptions / anything flagged as outside the standard conventions

See `0000-example.md` in this folder for the exact template.

## Why

- Gives everyone on the project a readable history of what the AI actually did, in order, without digging through git log messages.
- Makes it easy to spot if the AI drifted outside `standards/`/`commands/` on a given change (check that file's **Notes** section).
- For the engine, keeps a running record of CPU and accuracy numbers across changes.
- Nothing in this folder should ever be deleted or rewritten — treat it like a log, not a living document.
