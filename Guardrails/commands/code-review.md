# /code-review

Use this to review a diff, PR, file, or module against FaceTrack's standards, without making changes unless asked.

## Arguments

`$ARGUMENTS` = a file path, folder, or PR/diff reference to review.

## Steps

1. Read the target code fully before commenting.
2. Check against each relevant file in `standards/`:
   - Architecture placement — business rules only in `backend/app/domain/`; queries only in repositories; thin routers and Celery tasks; no attendance logic in the engine or frontend (`02-backend-architecture.md`, `07-frontend-architecture.md`, `15-business-logic-and-duplication.md`)
   - Naming and async rules — no blocking calls inside `async def` (`03-fastapi-coding-standards.md`, `07-frontend-architecture.md`)
   - API conventions, envelope, status codes, `response_model`, generated client updated (`04-rest-api-standards.md`, `08-frontend-state-and-api-layer.md`)
   - Database — N+1 queries, missing indexes, unsafe migrations, missing `downgrade()`, raw SQL without bound parameters (`05-database-postgresql.md`)
   - Security — hardcoded secrets/RTSP URLs, missing permission or department-scope checks, frontend-only auth, CORS/cookie settings (`06-security-and-auth.md`)
   - Engine — unbounded queues, processing every frame, embedding outside best-crop selection, thread budgets, new CPU work outside the degradation ladder, GPU dependencies, threshold changes, missing benchmark numbers (`17-recognition-engine-cpu.md`)
   - Privacy — consent check on enrollment, no raw video, biometric data in logs, retention/erasure as hard delete, audit logging (`18-privacy-and-biometric-data.md`)
   - Error handling / logging (`09-forms-errors-logging.md`)
   - Duplication — does this reimplement something in `common/` or elsewhere? (`15-business-logic-and-duplication.md`)
   - Test coverage and requirement IDs in tests (`11-testing.md`)
3. Categorize findings:
   - **Must fix** — bugs, security/privacy issues, wrong-person risk, broken conventions, CPU/backlog risks
   - **Should fix** — maintainability/consistency issues
   - **Nit** — minor style preferences, optional
4. For each finding, cite the specific standards file/rule it violates, not just an opinion.
5. Do not rewrite the code as part of a review unless explicitly asked to also fix it — a review reports, it doesn't silently patch.

## Batch Log

A pure review (findings only, no code touched) does **not** need a batch log. If the user then asks you to also apply fixes from the review, that follow-up work is a real code change — create a batch log per `CLAUDE.md` §7 (`Type: review-fix`) once those fixes are made.
