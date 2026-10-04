# FaceTrack runbook

Operating guide for IT (requirements §15, §18, §19). It covers deployment, engine nodes, certificates, backups, monitoring, keys, maintenance and upgrades. Everything runs on-premise with Docker Compose. There are no cloud services and no GPUs.

> **Status:** These steps were exercised on a single development host (see `batch/*_docker-deployment-monitoring.md` for what was and was not run). They have not been run on the production servers, against real cameras, or with the organisation's CA, SMTP or Teams.

> **Laptop or test machine:** to run everything, including one recognition engine, on a single Windows laptop, follow [`docs/local-development.md`](local-development.md) (`infra/docker-compose.dev.yml`). That setup is not for production.

## 1. Topology

| Host | Compose file | Services | Exposed |
|---|---|---|---|
| Backend server | `infra/docker-compose.yml` | nginx (portal + TLS), backend (FastAPI/Gunicorn), worker (Celery), scheduler (Celery beat, exactly one), migrate (one-shot), postgres (+pgvector), redis (AOF), mediamtx (live view), backup, prometheus, alertmanager, grafana, node-exporter | LAN: 443, 80 (redirect only), 8189/udp (WebRTC media). Isolated VLAN (`INTERNAL_BIND_IP`): 5432, 6379, 9090 |
| Engine node ×N | `infra/docker-compose.engine.yml` | engine (CPU only, pinned cores) | VLAN: 8100 (backend API calls, Prometheus) |

Cameras are reached only by the engine nodes (RTSP) and by MediaMTX (live view, on demand). The engine VLAN has no inbound internet access (§15).

Request paths: browser → Nginx → `/api`, `/ws` (backend), `/webrtc` (MediaMTX WHEP signalling), `/grafana`. `/internal/*` and `/metrics` are not reachable through Nginx.

## 2. First deployment (backend server)

Prerequisites: Docker Engine 25+ with the Compose plugin, the server's VLAN and LAN addresses, a DNS name for the portal, and a certificate from the organisation's CA.

1. **Get the code and images.** Clone the repository at the release tag. Build with `docker compose build` or pull from the internal registry (`REGISTRY`, `FACETRACK_VERSION` in `infra/.env`).
2. **Create the configuration** (never commit these files; `.gitignore` covers them):
   ```bash
   cd infra
   cp .env.example .env                       # addresses, passwords, paths, alert routing
   cp env/backend.env.example env/backend.env # application settings
   chmod 600 .env env/backend.env
   ```
   Replace every `change-me`:
   - Passwords and `BACKUP_ENCRYPTION_KEY`: `openssl rand -hex 32`. Use hex: the database and Redis passwords go into connection URLs, where a `/` (common in base64) breaks the Redis URL.
   - `JWT_SECRET`: `python3 -c "import secrets;print(secrets.token_urlsafe(48))"`.
   - `ENCRYPTION_KEY` (AES-256, the **same value on every engine node**): `python3 -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`.
   - `ENGINE_API_TOKEN`: `openssl rand -hex 32`, the same on the backend and every engine.

   **Store all of them in the organisation's password vault.** Losing `ENCRYPTION_KEY` makes every face embedding, camera URL and snapshot unreadable. Losing `BACKUP_ENCRYPTION_KEY` makes every backup useless.
3. **Media directory.** Create `MEDIA_DIR` owned by uid 10001 (`sudo install -d -o 10001 -g 10001 -m 750 /srv/facetrack/media`). With engine nodes on other hosts, this is an NFS export mounted at the same path on every host (§4).
4. **TLS certificate.** Put the organisation-issued `fullchain.pem` and `privkey.pem` (mode 600) in `infra/nginx/certs/`. For a test system only, `sh nginx/gen-dev-cert.sh <name>` makes a self-signed pair.
5. **Start:**
   ```bash
   docker compose up -d
   docker compose ps            # migrate: exited (0); backend, worker: healthy
   ```
   The `migrate` service runs `alembic upgrade head` before the backend, worker and scheduler start. The PostgreSQL init script (`infra/postgres/init/10-engine-role.sh`) creates the engine's read-only role `facetrack_engine` the first time the volume is created.
6. **First Super Admin** (once; keep the password out of files and shell history):
   ```bash
   read -rs PW; docker compose run --rm -e SEED_ADMIN_USERNAME=admin -e SEED_ADMIN_EMAIL=it@example.org \
     -e SEED_ADMIN_PASSWORD="$PW" backend python -m app.scripts.seed; unset PW
   ```
7. **Check:**
   - `https://<SERVER_NAME>/` shows the sign-in page, and `https://<SERVER_NAME>/api/v1/health` returns success.
   - Sign in, then set Settings › General (timezone), locations, departments and shifts.
   - `https://<SERVER_NAME>/grafana/` (user `GRAFANA_ADMIN_USER`) shows the *FaceTrack overview* dashboard. In Prometheus (`http://<INTERNAL_BIND_IP>:9090/targets`) the backend, mediamtx, node and prometheus targets are up.
   - Run a first backup and a restore test (section 6).

## 3. Engine nodes

For each CPU server (requirements §18; the Phase 2 gate was 16 cameras per node):

1. `cp infra/env/engine.env.example infra/env/engine.env` and fill in:
   - `ENGINE_NODE_NAME` (unique, e.g. `node-2`);
   - `ENGINE_DATABASE_URL`: the read-only `facetrack_engine` role, with `ENGINE_DB_PASSWORD`, at the backend's VLAN address;
   - `ENGINE_REDIS_URL`;
   - `ENGINE_ENCRYPTION_KEY` (= backend `ENCRYPTION_KEY`) and `ENGINE_API_TOKEN`.
2. In `infra/.env` on that host, set:
   - `INTERNAL_BIND_IP` (the node's VLAN address);
   - `ENGINE_CPUSET`, `ENGINE_CPUS` and `ENGINE_MEMORY`. Leave cores for the OS. Keep `ENGINE_INFERENCE_WORKERS × ENGINE_THREADS_PER_WORKER` within the pinned cores.
3. Mount the shared media directory at `MEDIA_DIR`, then run `docker compose -f docker-compose.engine.yml up -d`. The image downloads the ONNX models at build time (pinned SHA-256); models are never committed.
4. On the backend server:
   - add the node to `ENGINE_NODES` in `env/backend.env` (e.g. `{"node-1": "http://10.20.0.11:8100", "node-2": "http://10.20.0.12:8100"}`), then run `docker compose up -d backend worker scheduler`;
   - add it to `infra/monitoring/prometheus/targets/engines.yml` (copy `engines.example.yml`; `node` = `ENGINE_NODE_NAME`). Prometheus reloads the file within a minute.
5. In the portal, assign cameras to the node (Cameras › edit › engine node). The Cameras screen shows each camera's status, FPS and lag once the node reports.

## 4. Media storage (snapshots, face crops, exports)

- One shared directory (ADR-0005; P2 pending). Every file is AES-256-GCM encrypted by the application. It is never a public share.
- Single host: a local directory. Several hosts: an NFS export from the backend server or a NAS, mounted at the same path. Use `sec=krb5p`, or restrict the export to the VLAN and keep it on the isolated VLAN.
- Retention runs nightly from Settings › Retention: snapshots and unknown faces 90 days; enrollment data until the employee leaves + 30 days. Report export files are deleted after 25 h.
- Back up the media directory with the organisation's file backup if snapshots must survive a disk loss. The database backup does not include it.

## 5. Certificates

- Production: organisation CA. Renew before expiry. Replace both files in `infra/nginx/certs/`, then run `docker compose exec nginx nginx -s reload`.
- Check expiry: `openssl x509 -enddate -noout -in infra/nginx/certs/fullchain.pem`. Put a reminder 30 days ahead in the IT calendar.
- Webcam enrollment and WebRTC only work over HTTPS with a certificate the browsers trust.

## 6. Backups and restore (§15)

- The `backup` container writes `BACKUP_DIR/facetrack-<date>-<time>.dump.gpg` every day at `BACKUP_TIME`. Each file is a `pg_dump` custom-format archive, encrypted with AES-256 (`BACKUP_ENCRYPTION_KEY`). Files older than `BACKUP_KEEP_DAYS` (30) are deleted. Copy `BACKUP_DIR` off the server with the organisation's backup system.
- Results go to Prometheus. The `BackupFailed` and `BackupMissing` (older than 26 h) alerts fire on problems.
- Run a backup now (also do this before every upgrade): `docker compose exec backup backup.sh --now`.
- **Quarterly restore test**: restore into a scratch database, check the counts, then drop it.
  ```bash
  docker compose exec backup ls -1t /backups | head -1
  docker compose exec backup restore.sh /backups/<file> facetrack_restore_test
  docker compose exec postgres dropdb -U facetrack facetrack_restore_test
  ```
  Record the date and result in the IT change log.
- Full disaster recovery onto a new server:
  1. Deploy as in section 2 with the same `.env` secrets.
  2. Stop backend, worker and scheduler.
  3. Restore into `facetrack` with `restore.sh` (use an empty database).
  4. Run `docker compose run --rm migrate`.
  5. Start everything.
  6. Restore the media directory from file backup.

  Redis holds only in-flight events and short-lived keys. Engines buffer events while Redis is down.

## 7. Monitoring and alerts (§18)

Prometheus scrapes:
- the backend (`/metrics` on the internal network);
- every engine node (`targets/engines.yml`);
- MediaMTX;
- node-exporter (disk, plus the backup textfile metrics).

Alertmanager sends to `ALERT_EMAIL_TO` and, when `TEAMS_WEBHOOK_URL` is set, to the Teams channel. Its secrets are written to files inside its volume, not to the config. The rules live in `infra/monitoring/prometheus/rules/facetrack.yml`; their tests are in `tests/`. Run them with `make check-monitoring`.

The application also emails admins directly (Settings › Notifications) when a camera goes offline or an engine fails, and on payroll/HR sync failures. Configure both channels.

| Alert | Meaning | First steps |
|---|---|---|
| `EngineDown` | Prometheus cannot reach an engine | `docker compose -f docker-compose.engine.yml ps` / `logs engine` on the node. Check the VLAN and the host's CPU and memory. Its cameras stop recognising until it is back; events already captured are kept in its disk buffer. |
| `CameraOffline` (> 5 min) | No video from a camera | Ping the camera. Check the RTSP URL and credentials (Cameras › Test connection), the NVR, and PoE. The engine reconnects by itself. If the error is 401/403 (wrong user or password), the engine waits `ENGINE_AUTH_RETRY_S` (default 15 min) before the next login, because cameras such as Dahua lock the account for about 30 minutes after a few failures. Save the corrected link (the camera is restarted and tried at once), or test it once with Test connection; do not test repeatedly with a doubtful password. |
| `EngineCpuHigh` (> 85%, 5 min), `DegradationLadderStep3` | The node is overloaded and recognition runs reduced | Check the camera count on the node, sub-streams, and idle rates. Move cameras to another node. |
| `CameraLagHigh` (> 2 s), `CameraFpsBelowTarget` (< 80% while ACTIVE) | Frames are processed late or too slowly | Same as CPU; also check network bandwidth from the camera. |
| `EngineEventsBuffered`, `EngineEventsLost` | The engine cannot reach Redis/backend; *lost* means the buffer filled up | Check Redis (`docker compose ps redis`), the VLAN and the firewall. Lost events need manual attendance entries for that period. |
| `EventQueueLag` (> 60 s) | The backend is behind on recognition events | Worker health and logs (`docker compose logs worker`). Scale the worker with `WORKER_CONCURRENCY`. |
| `EventsDeadLettered` | Some events failed 10 times or were malformed | `docker compose exec redis redis-cli -a "$REDIS_PASSWORD" XRANGE recognition.events.dead - + COUNT 20`, then fix the cause (often an unknown camera ID). Never edit the stream by hand. |
| `DayCloseStale` | The day-close job is not finishing | Scheduler and worker logs. Absent / Missing check-out are not being set. |
| `PayrollPushFailed`, `HrSyncFailed` | An integration failed after its retries | Worker logs (`integration`), the remote system's status and credentials. Push again from Settings › Integration › Run now; unsent days are included automatically. |
| `DiskAbove80Percent` | Disk filling | Check `MEDIA_DIR`, `BACKUP_DIR`, Docker logs and Prometheus data. Confirm the retention jobs ran (Audit log, `retention.*`). |
| `BackupFailed`, `BackupMissing` | No good backup | `docker compose logs backup`. Check disk space and the `postgres` service. Run `backup.sh --now`. |
| `BackendDown`, `MediaMtxDown` | API / live view down | `docker compose ps`, `logs backend` / `logs mediamtx`. A MediaMTX outage affects live view only, not attendance. |

Logs are JSON on stdout, rotated by Docker (20 MB × 5 per container): `docker compose logs -f --since 1h <service>`. Request IDs from Nginx (`X-Request-ID`) appear in the backend logs. Face images, embeddings, passwords and tokens are never logged.

## 8. Keys and credentials

| Secret | Where | How to rotate | Effect |
|---|---|---|---|
| `JWT_SECRET` | backend.env | New value, then `docker compose up -d backend worker` | Every user is signed out |
| `ENGINE_API_TOKEN` | backend.env + every engine.env | Change everywhere, restart backend and engines together | Enrollment and camera tests fail between the two restarts |
| `ENCRYPTION_KEY` | backend.env + every engine.env | **Not supported yet** (P12). Embeddings, camera URLs and stored files are encrypted with it and there is no re-encryption tool | Changing it makes existing data unreadable |
| `BACKUP_ENCRYPTION_KEY` | .env | New value applies to new backups. Keep the old key until the last backup made with it has expired (30 days) | — |
| PostgreSQL `facetrack` / `facetrack_engine` passwords | .env (+ engine.env) | `ALTER ROLE … PASSWORD …` in psql, then update the env files and restart | Short outage |
| `REDIS_PASSWORD` | .env + engine.env | Change, then restart redis, backend, worker, scheduler and the engines | Engines buffer events meanwhile |
| Payroll/HR API keys | Settings › Integration | Create a new key, switch the payroll system to it, revoke the old one | No outage |
| `GRAFANA_ADMIN_PASSWORD` | .env | Change in Grafana (the env value applies only on first start) | — |

## 9. Regular maintenance (§18)

- **Monthly threshold review** (recognition owner + HR):
  - Look at the voided events (Event log, status *Voided*) and the reasons given.
  - Look at the unknown faces that were later assigned to an employee.
  - Compare cameras using the Event log's camera filter.

  More wrong-person voids means raising `recognition.match_thresholds` (or that camera's own threshold) or `recognition.margin`. Many assigned unknowns from known employees means checking enrollment quality and camera placement first. **Never lower a threshold without the recognition owner's approval.** The portal asks for confirmation, and every change is in the audit log.
- **Quarterly:**
  - restore test (section 6);
  - re-enrollment prompt for employees whose match scores are trending down;
  - review user accounts and roles (Settings › Users);
  - review API keys (revoke unused ones; check *last used*).
- **Monthly patching:**
  - OS updates;
  - rebuild the images on the current base images, scan them (CI runs Trivy) and deploy as in section 10.

## 10. Upgrades

1. Read the release notes and the `batch/` logs for migrations and new settings. Compare `infra/.env.example` and `env/*.env.example` with your files.
2. `docker compose exec backup backup.sh --now` (§18: production deploys take a backup first).
3. `FACETRACK_VERSION=<tag>`, then `docker compose pull` (or `build`), then `docker compose up -d`. `migrate` runs before the backend starts. Watch `docker compose ps` and the Grafana dashboard.
4. Engine nodes: one at a time with `docker compose -f docker-compose.engine.yml up -d`. Its cameras pause for about a minute, and buffered events are delivered after the restart.
5. Rollback:
   1. Set the previous `FACETRACK_VERSION`.
   2. If the release had a migration, run `docker compose run --rm backend alembic downgrade -1` **before** starting the old images. Every migration has a tested downgrade.
   3. Run `docker compose up -d`.

## 11. Useful commands

```bash
docker compose ps                                   # state and health
docker compose logs -f --since 30m backend worker   # follow logs
docker compose exec backend alembic current         # schema version
docker compose run --rm migrate                     # apply migrations
docker compose exec postgres psql -U facetrack      # database shell
docker compose restart scheduler                    # only one scheduler may run
make check-monitoring                               # promtool + amtool checks and alert rule tests
```
