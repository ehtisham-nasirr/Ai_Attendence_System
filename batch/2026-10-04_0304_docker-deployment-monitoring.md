# Batch: docker-deployment-monitoring

**Date:** 2026-10-04 03:04
**Type:** feature
**Command Used:** commands/new-feature.md (infra), commands/fix-bug.md (defects found by the deployment test)
**Standards Referenced:** standards/01, 06, 12, 13, 15, 16, 17, 18
**Requirements:** §15 (TLS, encrypted backups kept 30 days and restore-tested, isolated VLAN, container scanning), §18 (deployment, CI/CD, monitoring and alerts, maintenance), §19 risks; FR-4, FR-40 (session), NFR-14

## Summary
Built the deployment and operations layer (build Phase 5; requirements §18):
- Docker Compose for the backend server and for each engine node;
- edge Nginx with TLS that also serves the portal;
- MediaMTX for live view only;
- encrypted nightly backups with a restore script;
- Prometheus with the §18 alert rules (unit-tested), Alertmanager (email + Teams), Grafana and node-exporter;
- a CI workflow, a runbook and a root README.

The whole stack was built from the real Dockerfiles and run locally. That run found and fixed seven defects that unit tests and `vite preview` could not show (see "Defects found and fixed").

## Changes Made
- **Backend server (`infra/docker-compose.yml`):**
  - Services: postgres (pgvector, port on the VLAN address only), redis (AOF, password), `migrate` (one-shot `alembic upgrade head`; the app services wait for it), backend (Gunicorn + Uvicorn workers, `backend/gunicorn.conf.py`), worker, scheduler (one beat), nginx, mediamtx, backup, prometheus, alertmanager, grafana, node-exporter.
  - Every service has log rotation and a restart policy; healthchecks where a check is meaningful.
- **Engine node (`infra/docker-compose.engine.yml`):** cpuset, CPU and memory limits; shared media mount; persistent event-buffer volume; port 8100 on the VLAN address.
- **Configuration:** `infra/.env.example`, `infra/env/{backend,engine}.env.example`. Secrets only in these git-ignored files. The seed password is passed with `-e` at run time, never stored.
- **Nginx (`infra/nginx/`):**
  - Multi-stage image (Node build of the portal → `nginx:stable-alpine`).
  - TLS 1.2/1.3, HSTS, a strict CSP (no `unsafe-eval`, no inline scripts), JSON access logs without query strings, and a login rate limit.
  - `/internal/` and `/metrics` return 404. Proxies `/api`, `/ws`, `/webrtc` (WHEP) and `/grafana`.
  - Upstreams are re-resolved through Docker DNS. `gen-dev-cert.sh` for test systems only.
- **MediaMTX:** WebRTC only. Every read is checked by the backend (`authMethod: http`, Q25). On-demand pulls. Paths are re-applied every 5 min by the new Beat task `sync_live_paths` (Q52).
- **PostgreSQL init:** a read-only `facetrack_engine` role with default privileges (Q51).
- **Backups (`infra/backup/`):**
  - `pg_dump` custom format, encrypted with GnuPG AES-256 (`BACKUP_ENCRYPTION_KEY`), files mode 600, 30-day retention.
  - Writes textfile metrics for node-exporter. `backup.sh --now`, and `restore.sh` for the quarterly test.
- **Monitoring (`infra/monitoring/`):**
  - Prometheus scrape config (engines through `targets/engines.yml` file discovery) and 19 alert rules covering every §18 alert, plus service-down, stale-job, lost-event and dead-letter alerts (Q49).
  - `promtool` unit tests for the alert rules.
  - Alertmanager config rendered from env at start, with secrets kept in 0600 files; `msteamsv2` (Q54); an inhibit rule (engine down hides its cameras' alerts).
  - Grafana datasource and an overview dashboard (engines, cameras, backend, jobs, disk).
- **CI (`.github/workflows/ci.yml`):**
  - On every push: ruff, mypy and pytest per Python package against pgvector and Redis services; the frontend's lint, typecheck, Vitest, build and `npm audit`.
  - `make check-monitoring` and `docker compose config`.
  - Image builds with a Trivy scan (fixable HIGH/CRITICAL fail).
  - Actions are pinned to existing tags; Trivy is pinned by commit.
- **Backend:**
  - Metrics for HR sync failures and last success.
  - Payroll failure counter only on the final failed attempt.
  - `sync_live_paths`.
  - Gunicorn entrypoint in the Dockerfile.
- **Removed:** `frontend/Dockerfile` and `frontend/nginx-spa.conf`, now covered by the Nginx image.
- **Docs:**
  - `docs/runbook.md`: topology, first deployment, engine nodes, media/NFS, certificates, backup/restore and DR, alert-response table, key rotation table, monthly and quarterly maintenance, upgrades and rollback.
  - Root `README.md`; Makefile targets `images` and `check-monitoring`.
  - `docs/open-questions.md`: P12, P13, Q49–Q56.

## Defects found and fixed (deployment test)
1. **Random sign-outs (backend, security):** the sliding-session refresh revoked the old token at once. Requests the portal had already sent in parallel then got 401 "session ended". The old token now stays valid for 60 s after a refresh; the grace is set once and not extended by re-use. Sign-out stays immediate (Q53). A regression test was added; it fails without the fix.
2. **Live view page broken behind Nginx:** `location /live/` 301-redirected the portal's `/live` page to MediaMTX. WHEP signalling moved to `/webrtc/` (backend default `MEDIAMTX_WEBRTC_PUBLIC_PATH=/webrtc`).
3. **CSP violation in the portal:** Zod 4 probes `new Function` (blocked without `unsafe-eval`). Fixed with `z.config({ jitless: true })` before any schema loads (`src/lib/zodConfig.ts`).
4. **Missing security headers on the portal:** an `add_header` inside a location dropped the server-level HSTS/CSP headers on `/` and `/assets/`. The headers are now in include files used in each such location.
5. **502 after a backend restart:** Nginx resolved upstream names once at start, so a recreated container's new IP was not seen until Nginx restarted. Upstreams now use `resolve` with Docker DNS. Verified by forcing a new IP.
6. **Backups readable by everyone:** the dump file was written with mode 666. The script now sets `umask 077`; only the metrics textfile is 644.
7. **Teams payload:** the app's alerts used the legacy MessageCard format, which Teams Workflows webhooks do not accept. They now send an Adaptive Card message (3 new tests).

Also changed:
- **Engine log noise:** the no-frame watchdog restarted offline cameras every 10 s, logging a warning each time. It now only acts on a connected but silent stream; the decoder's backoff handles reconnects (Q56, test added).
- **Scheduler health:** it inherited the image's HTTP healthcheck and would show as unhealthy. That check is now disabled for the scheduler; a stalled scheduler raises `DayCloseStale`.
- **Small Nginx improvement:** `/api` now uses HTTP/1.1 keepalive to the backend.

## Files Changed
```
infra/docker-compose.yml, infra/docker-compose.engine.yml, infra/.env.example, infra/env/{backend,engine}.env.example
infra/nginx/{Dockerfile,nginx.conf,gen-dev-cert.sh,certs/.gitkeep}, infra/nginx/templates/{facetrack.conf.template,proxy_params,security_headers,portal_csp}
infra/mediamtx/mediamtx.yml, infra/postgres/init/10-engine-role.sh, infra/backup/{Dockerfile,backup.sh,restore.sh}
infra/monitoring/prometheus/{prometheus.yml,rules/facetrack.yml,tests/facetrack_test.yml,targets/engines.example.yml}
infra/monitoring/alertmanager/{alertmanager.yml.tmpl,render-and-run.sh}, infra/monitoring/grafana/{provisioning/**,dashboards/facetrack-overview.json}
backend/Dockerfile, backend/gunicorn.conf.py, backend/.env.example, backend/app/core/{config,security}.py, backend/app/ws/live.py
backend/app/services/{teams,metrics_store}.py, backend/app/domain/cameras/service.py, backend/app/worker/{schedule.py,tasks/cameras.py,tasks/integration.py}
backend/tests/api/{test_auth,test_cameras_settings}.py, backend/tests/domain/test_camera_status.py, backend/tests/services/test_teams.py
engine/app/pipeline/camera_worker.py, engine/tests/test_camera_worker.py
frontend/src/main.tsx, frontend/src/lib/zodConfig.ts, frontend/README.md; removed frontend/Dockerfile, frontend/nginx-spa.conf
.github/workflows/ci.yml, Makefile, README.md, .gitignore, docs/runbook.md, docs/open-questions.md
```

## Database Changes
None (no migration). The engine role is created by the PostgreSQL init script.

## Testing
- **Unit and integration suites, all passing:**
  - backend 155 (new: session-refresh race, Teams payload ×3, `sync_live_paths`), coverage 86%, ruff/mypy clean;
  - engine 110 + 2 skipped (new: watchdog leaves offline cameras to backoff);
  - common 45;
  - frontend 50 Vitest, with ESLint, `tsc` and build clean.
- **Monitoring config:**
  - `promtool check config` and `check rules` (19 rules);
  - `promtool test rules`: camera offline only after 5 min; CPU > 85% for 5 min; low FPS only while ACTIVE; backup missing after 26 h and not before; queue lag.
  - Alertmanager template rendered in the real image and passed `amtool check-config`, both with and without Teams.
- **Compose:** `docker compose config` passes for both files, with the example env files as in CI.
- **Images:** backend, nginx, backup and engine were built from the real Dockerfiles (backend 1.0 GB, nginx 96 MB, backup 444 MB, engine 3 GB, models downloaded with pinned SHA-256).
  - In this sandbox the build containers can only reach the internet through the session's HTTPS proxy. The builds therefore used scratch copies of the Dockerfiles that add only the proxy and CA settings after each `FROM`; the committed Dockerfiles are unchanged.
- **Full stack run (`docker compose up`, self-signed certificate, generated throwaway secrets), all verified:**
  - Startup: migrate exits 0 before the app starts; backend, worker and nginx healthy; the engine's read-only role exists (SELECT yes, INSERT no).
  - HTTPS: HTTP → HTTPS redirect; HSTS and CSP on pages, assets and API; `/internal/*`, `/metrics` and `/api/v1/../metrics` give 404; `/api/v1/health` reports database and Redis ok.
  - Admin and API: Super Admin created with `docker compose run -e SEED_ADMIN_*`; sign-in; a report preview; a **PDF export produced by the Celery worker container** and downloaded through Nginx.
  - WebSocket `/ws/live` upgrade (101) through Nginx.
  - Engine node: the **real engine image** ran as `node-1` against the stack. It loaded the camera through the read-only role, reported status and load to the backend, and was scraped by Prometheus. The camera's RTSP credentials never appeared in logs or the UI.
  - Live view: WHEP without a token or with a bad token → 401; with the token from `/cameras/{id}/live` → authorised, and MediaMTX starts the on-demand pull (times out because the test address has no camera).
  - Alerting end to end: the offline test camera raised **CameraOffline**, pending at 21:46:22 and firing 5 minutes later. Alertmanager received it with the node label and attempted email (no SMTP here). `BackupFailed` fired on a forced failure and cleared after the next success. `DiskAbove80Percent` fired for this host's real 93% disk.
  - Backup: `backup.sh --now` produced an AES-256 GnuPG file (mode 600). `restore.sh` restored it into a scratch database (users present), which was then dropped. A forced failure (bad host) exits 1, sets `last_run_success 0` and keeps the last success time.
  - Grafana at `/grafana/`: the dashboard is provisioned and the Prometheus datasource is healthy.
  - Nginx kept working after the backend container was recreated with a **different IP**.
- **End to end against the deployed stack:** the Playwright suite (portal walk-through of every screen, reports + Excel/PDF downloads + API key pull, tablet drawer) **passed 3 runs in a row with 0 console errors** through Nginx, TLS and the production CSP. Before the fixes above it failed.
- **Not verified:**
  - the CI workflow itself (GitHub Actions cannot run here; push access is still refused, P10);
  - Trivy results;
  - production servers, an NFS mount, the organisation's CA certificate, real SMTP and Teams delivery (P7);
  - WebRTC media to a browser (no camera; UDP 8189 path not exercised);
  - multi-node engines on separate hosts and a VLAN;
  - the `rslave` root mount of node-exporter (refused by this sandbox's mount setup, so the trial used a plain read-only mount; standard on normal Linux hosts);
  - the 72-hour soak and load tests (§17);
  - long-running scheduled jobs at real clock times.

## Notes
- Pending owner input: P12 (`ENCRYPTION_KEY` rotation policy; no re-encryption tool yet) and P13 (registry, staging and deploy approval for CI/CD). P2 (object store), P7 (SMTP/Teams) and P10 (GitHub push) are unchanged.
- Decisions: Q49–Q56.
- No new application libraries. New infrastructure images: `prom/prometheus`, `prom/alertmanager`, `grafana/grafana-oss`, `prom/node-exporter`, `bluenviron/mediamtx`, `nginx:stable-alpine`, `postgres:16-alpine` (backup). The CI uses `aquasecurity/trivy-action`.
- The trial stack, its volumes, the generated secrets and the dev certificate were removed after the test. Built images remain only in this sandbox.
