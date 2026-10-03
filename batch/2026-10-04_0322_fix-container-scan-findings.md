# Batch: fix-container-scan-findings

**Date:** 2026-10-04 03:22
**Type:** bugfix
**Command Used:** commands/fix-bug.md
**Standards Referenced:** standards/06-security-and-auth.md, standards/12-git-standards.md, standards/16-change-management-and-workflow.md
**Requirements:** §15 (container vulnerability scanning in CI), §18 (CI/CD)

## Summary
The first GitHub Actions run passed every lint, type-check and test job. It failed only the Trivy image scan: all four images had HIGH/CRITICAL vulnerabilities that already have fixed versions. The images now apply OS security updates at build time, and the backup image drops the unused `gosu` binary.

## Changes Made
- `backend/Dockerfile`, `engine/Dockerfile`: `apt-get upgrade -y` before installing packages (pcre2 CVE-2026-103111, HIGH).
- `infra/nginx/Dockerfile`: `apk upgrade --no-cache` in the final stage (libexpat CVE-2026-93990 and pcre2, both HIGH).
- `infra/backup/Dockerfile`: `apk upgrade --no-cache` and removal of `/usr/local/bin/gosu`. That is the postgres server image's Go helper, built with an old Go and carrying 22 CVEs (1 CRITICAL); this image only runs the pg_dump, pg_restore and gpg clients.

## Files Changed
```
backend/Dockerfile
engine/Dockerfile
infra/nginx/Dockerfile
infra/backup/Dockerfile
```

## Database Changes
None.

## CPU / Performance Impact
N/A (image build only; engine runtime code unchanged).

## Testing
- **Reproduced:** the CI run https://github.com/ehtisham-nasirr/Ai_Attendence_System/actions/runs/37157561120 failed the scan on all four images (backup 22, nginx 2, backend 1, engine 1).
- **After the fix:** all four images were rebuilt locally (through the sandbox proxy, with the same proxy-only Dockerfile copies as the Phase 5 batch) and scanned with `aquasec/trivy:latest` using `--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`. Result: 0 findings and exit 0 for each image.
- The backup image still has pg_dump/pg_restore 16.15 and GnuPG 2.4.9; nginx is 1.30.5.
- **Not verified:** the CI re-run, which happens on this push.

## Notes
- New CVEs are published continually, so the scan can fail again later without any code change. The fix then is a rebuild, or a bump of the base image.
- Seen but not changed (outside this fix): the backend and engine images keep uv's download cache under `/root/.cache/uv`. This makes the images larger; it can be dropped with `UV_NO_CACHE=1` in a later change.
