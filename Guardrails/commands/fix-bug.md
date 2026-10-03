# /fix-bug

Use this for any bug-fix request (e.g. "night shift check-out lands on the wrong day", "camera stays in ACTIVE mode forever", "manager can see other departments' attendance").

## Before Starting

Read `standards/15-business-logic-and-duplication.md` § Refactoring Rule and `CLAUDE.md` § Mandatory Rules. If the bug is in the engine, also read `standards/17-recognition-engine-cpu.md` and follow the measurement steps of `commands/engine-change.md` for the fix.

## Steps

For `$ARGUMENTS` (the bug description):

1. **Reproduce/understand the bug first.** Trace it to its root cause — engine, `common/`, backend, frontend, or configuration. Do not guess-fix based on symptoms.
2. **Locate the single authoritative place** the rule lives (domain service, engine pipeline, `common/` schema, permission dependency) — see `standards/15-business-logic-and-duplication.md`. If the same rule is duplicated and only one copy is wrong, flag the duplication; don't just patch the one you found.
3. **Apply the refactoring rule, in order:**
   - First: the smallest safe change that correctly fixes it.
   - Second: refactor the affected area only if the current structure makes a correct fix impossible.
   - Third: a larger architectural change — only if explicitly requested or clearly unavoidable.
4. **Do not** turn this into an unrelated rewrite. Do not touch files outside the bug's actual blast radius.
5. **Check for regressions and data impact:** does the fix change behaviour elsewhere? Were existing `attendance_days` rows calculated wrongly? If so, propose (don't silently run) a recalculation/data fix.
6. **Add or update a test** that would have caught this bug, named with the requirement ID where possible.
7. **Verify the fix** — run the affected flow and relevant tests. State plainly what was and wasn't verified.
8. **Create a batch log file in `batch/`** per `CLAUDE.md` §7 — required, even for a one-line fix. Use `Type: bugfix`.
9. **Report** using the Final AI Response Format in `CLAUDE.md`, including a one-line root-cause explanation.
