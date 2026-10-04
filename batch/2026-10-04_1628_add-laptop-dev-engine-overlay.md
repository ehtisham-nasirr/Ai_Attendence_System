# Batch: add-laptop-dev-engine-overlay

**Date:** 2026-10-04 16:28
**Type:** feature
**Command Used:** commands/new-feature.md (scaled to infra + docs)
**Standards Referenced:** standards/01-project-structure.md, standards/06-security-and-auth.md, standards/12-git-standards.md, standards/13-documentation-and-comments.md, standards/16-change-management-and-workflow.md, standards/17-recognition-engine-cpu.md, standards/18-privacy-and-biometric-data.md
**Requirements:** FR-8, FR-9 (enrollment needs the engine), FR-1/FR-3 (cameras and their status), §18 (deployment); CLAUDE.md §1.3 (development uses recorded video only)

## Summary
The owner runs the backend stack on a Windows laptop. **Employees › Enroll** failed with "The recognition engine is unavailable. Please try again shortly.", because no engine runs there: `docker-compose.engine.yml` is meant for separate engine servers. A new dev-only Compose overlay adds one engine to the laptop stack. A step-by-step Windows guide (`docs/local-development.md`) covers the whole setup and every problem the owner has hit so far. `engine/README.md` described a `make dev` that did not exist; `make dev` now starts this overlay, and the sentence is fixed. Fixes from an independent review are included (media write check, line-ending check, ZIP updates, the expected nginx Grafana log line).

## Changes Made
- **`infra/docker-compose.dev.yml` (new).** Used as `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`, on one laptop or test machine only. It adds an `engine` service:
  - built from `engine/Dockerfile`, image `${REGISTRY}/engine:${FACETRACK_VERSION}`, on the `internal` network as `engine` (matches backend `ENGINE_NODES={"node-1": "http://engine:8100"}`); no published port.
  - the read-only `facetrack_engine` DB role and Redis, with `ENGINE_DB_PASSWORD` and `REDIS_PASSWORD` interpolated from `infra/.env`;
  - the same media path as the backend (`MEDIA_DIR` → `/srv/media`), a persistent `engine-buffer` volume, and `./data/videos` → `/srv/videos` read-only for recorded clips;
  - `ENGINE_NODE_NAME=node-1`, `ENGINE_ENVIRONMENT=development`, `ENGINE_ALLOW_FILE_SOURCES=true`;
  - laptop CPU budget: 1 inference worker × 2 threads, no core pinning, `cpus` from `ENGINE_DEV_CPUS` (default 2), memory cap `ENGINE_DEV_MEMORY` (default 3g). These are separate from the server-sized `ENGINE_CPUS`/`ENGINE_MEMORY` (14 / 12g) that are already in the owner's `infra/.env`;
  - depends on postgres/redis healthy and migrate completed. Healthcheck requires `"status":"ok"` (worker, DB and Redis all up); the image's own check passes on any HTTP 200. `restart: always`, 30 s stop grace, the same log rotation as the other services.
  - Secrets: `env_file: env/engine.env` holds only `ENGINE_ENCRYPTION_KEY` and `ENGINE_API_TOKEN`. The guide creates the file from `env/backend.env` with one command, so nothing is typed or hardcoded. Every other engine setting is in the overlay's `environment`, which wins over the env file, so a copy of `engine.env.example` also works.
  - On the laptop, the backup, prometheus, alertmanager, grafana and node-exporter services get the profile `ops`. Plain `up -d` starts exactly the set the owner already runs, plus the engine; `--profile ops` adds the rest.
- **`Makefile`:** `dev-up` (`up -d --build`), `dev-down` (`down`, never `-v`), `dev-logs [S=service]`, all wrapping the overlay. `dev` is an alias of `dev-up`, so the `make dev` named in standards/01, standards/11, standards/13, commands/new-feature.md and requirements §19 rule 8 works.
- **`docs/local-development.md` (new).** Plain-English guide for the owner. It covers:
  - Rancher Desktop with dockerd (moby), Kubernetes off, WSL integration with Ubuntu, and docker only from Ubuntu;
  - getting the code with a git bundle or ZIP, and the one-time line-ending re-checkout;
  - `infra/.env` and `env/backend.env` for localhost: `CORS_ORIGINS` equal to the browser URL; hex for passwords; `ENCRYPTION_KEY` as base64 of 32 bytes; PowerShell and Ubuntu commands to make them;
  - the `env/engine.env` command, and an optional `COMPOSE_FILE` line so every `docker compose` command includes the engine;
  - the dev certificate (Ubuntu, or Git Bash with `MSYS_NO_PATHCONV=1` / `OPENSSL_CONF`), plus optional Windows trust for the webcam;
  - the first build's internet needs (Docker Hub, ghcr.io, PyPI, npm, huggingface.co; hotspot if blocked);
  - starting and checking the stack, the first admin, enrollment rules (3–10 photos, one face, face ≥ 112 px, consent);
  - testing with a recorded clip: `infra/data/videos`, `file:///srv/videos/<clip>.mp4` on `node-1`, development only, no live view for file sources;
  - daily start/stop, and a troubleshooting table. The table has every problem the owner hit (GitHub blocked, CRLF, OPENSSL_CONF, docker not found, Hyper-V socket timeout, 403 = CORS_ORIGINS mismatch, "recognition engine is unavailable") and a tested repair for a missing or out-of-date `facetrack_engine` DB role.
- **Links:** root `README.md` (kept in its existing UTF-16LE encoding) and `docs/runbook.md`.
- **`engine/README.md`:** replaced the false `make dev` sentence with the overlay, `infra/data/videos` and the no-live-view note.
- **Defect fixed in the docs/examples (found while writing the guide):** `infra/.env.example` and runbook §2 said to make passwords with `openssl rand -base64 36`. A `/` in a base64 password breaks the Redis URL (`ValueError: Port could not be cast to integer value`, checked with the backend's redis-py). About half of such passwords contain `/`. Both now say `openssl rand -hex 32`. Existing working installs are not affected.
- **`infra/.env.example`:** commented `COMPOSE_FILE`, `ENGINE_DEV_CPUS` and `ENGINE_DEV_MEMORY` lines for laptops.
- **`.github/workflows/ci.yml`:** the compose check now also validates the overlay.
- **`docs/open-questions.md`:** Q57 records these decisions.
- **Fixes from the independent review (same unit of work):**
  - `docs/local-development.md` step 6: new check that the containers (uid 10001) can write to `infra/data/media` (`touch /srv/media/.w … echo media ok`). New troubleshooting row for `Permission denied: '/srv/media/...'` (Enroll then shows "An unexpected error occurred."): `sudo chown -R 10001:10001 data/media` on a Linux file system; on `D:` send IT the `ls -ldn` output. An accepted enrollment photo is written there (`enrollment.py:136-137`); a rejected one is not, so the first test never reached this path.
  - Step 3, line endings: a check (`git ls-files --eol | grep -c 'w/crlf'`, run the fix if it is not `0`) replaces "cloned before 4 October 2026". `.gitattributes` came in at 12:40 Pakistan time that day, so a copy made earlier the same day was wrongly told to skip the step.
  - Step 3, ZIP updates: stop the system, copy the env files and certificates, and **move** `infra/data/` (encrypted enrollment photos, snapshots, test clips) into the new folder. Before, it was left behind, while the database (named volume) carried over and pointed at missing files.
  - Step 4.5 and troubleshooting: without `--profile ops`, nginx logs `grafana could not be resolved` about every 11 s and `/grafana/` gives 502. Documented as expected. The production nginx template is unchanged.
  - `make dev` alias (above); the guide and `engine/README.md` now name `make dev`. Q57 mentions the Grafana log line and the alias.

## Files Changed
```
infra/docker-compose.dev.yml            (new)
docs/local-development.md               (new)
infra/.env.example
Makefile
engine/README.md
README.md
docs/runbook.md
docs/open-questions.md
.github/workflows/ci.yml
batch/2026-10-04_1628_add-laptop-dev-engine-overlay.md
```
`docker-compose.yml`, `docker-compose.engine.yml`, the Dockerfiles and all application code are unchanged.

## Database Changes
None. No migration.

## CPU / Performance Impact
No engine code, model, threshold or scheduling change. This only sets a laptop budget: 1 worker × 2 threads, capped at 2 CPUs and 3 GB. Measured in this sandbox with `docker stats` (4 vCPU host), one synthetic 1280×720 25 fps clip on an ENTRY camera:
- engine: 3–19 % of one core across 8 samples; about 445–450 MiB memory (limit 3 GiB);
- the camera was ACTIVE at every check, `fps_actual` 2.4–3.6 against a target of 4, lag 0.02–0.03 s.

Not measured on the owner's laptop or a reference server.

## Testing
All run for real in this sandbox:
- **Compose config, as in CI.** Clean copy of `infra/` with the example env files: `docker compose config -q` passes for the base file, `docker-compose.engine.yml` and base + dev overlay. With the overlay the default service list is postgres, redis, migrate, backend, worker, scheduler, nginx, mediamtx, engine; `--profile ops` adds the other five. The engine's resolved `environment` overrides the production example values (workers 1, development, file sources on). A missing `env/engine.env` gives `env file .../infra/env/engine.env not found`. The `COMPOSE_FILE` line in `.env` works. `ci.yml` parses as YAML.
- **Real stack with the overlay.** Images were the current-Dockerfile builds `facetrack/{backend,nginx,engine}:scan`, re-tagged `:latest`; application code is unchanged since they were built. Run with `--no-build --pull never`. Extra settings for this sandbox:
  - throwaway hex secrets in git-ignored `infra/.env` and `infra/env/backend.env`;
  - `env/engine.env` made with the exact command from the guide (values matched backend.env; also checked with CRLF input);
  - `PUBLIC_BIND_IP=127.0.0.3`, `CORS_ORIGINS=["https://localhost","https://127.0.0.3"]`, `ENVIRONMENT=development`;
  - a dev certificate from `sh infra/nginx/gen-dev-cert.sh localhost`;
  - the scratch port-reset override, because the host already uses 5432 and 6379.
- **Results:**
  - engine `healthy` about 35 s after start. `/health`: `status ok, workers_alive 1, redis_ok, database_ok`. Env, mounts, `cpus=2`, `mem=3g`, `restart=always` and no published ports confirmed with `docker inspect`. The other services were healthy, migrate `Exited (0)`, and nginx started without Grafana;
  - `GET https://127.0.0.3/api/v1/health` (curl `--noproxy '*' -k`): `database ok, redis ok`;
  - Super Admin seeded with `docker compose run --rm -e SEED_ADMIN_...` (`seed complete`). Sign-in through the API worked: cookie jar, `X-CSRF-Token` from `ft_csrf`, `Origin: https://127.0.0.3`;
  - created a location, department, shift and employee `T-001` (consent date set);
  - **enrollment** with a synthetic no-face JPEG (stripes, made with PIL) → HTTP 422 "No photo was accepted.", `rejection_reason: "no_face"`. The engine judged the photo. For contrast, the same upload with the engine container stopped → HTTP 503 "The recognition engine is unavailable. Please try again shortly." (the owner's error). After restart it was healthy again;
  - **recorded clip:** `engine/scripts/sample_video.py` (synthetic, no faces) wrote a 30 s clip to `infra/data/videos/synthetic.mp4`. Camera "Trial clip" (ENTRY, `file:///srv/videos/synthetic.mp4`, `node-1`) was created. About 11 s later `GET /api/v1/cameras` showed `status online` and runtime `connected: true, mode ACTIVE, fps_actual 2.4`. The engine's `/cameras/status` showed `fps_actual 3.6, last_error null`. MediaMTX logged `invalid source: 'file://...'`, which confirms that live view cannot show file sources (documented);
  - **role repair (guide 11.1):** after dropping `facetrack_engine`, the engine restart-looped with `password authentication failed for user "facetrack_engine"`. The guide's three commands fixed it: `DROP OWNED`/`DROP ROLE` (errors harmlessly when the role is missing), the init script, then `restart engine`. The engine was healthy again with its camera running. Tested with the role present and with it missing;
  - editing `env/backend.env` and running plain `up -d` recreated backend, worker, scheduler and migrate (supports the guide's "after editing an env file" advice);
  - `make -n dev-up dev-down dev-logs` print the expected commands; `make dev-logs S=engine` followed the engine logs;
  - `git clone -b main <bundle>` worked with the existing bundle.
- **Re-run after the review fixes** (same images, throwaway env files from the same generator, `INTERNAL_BIND_IP`/`PUBLIC_BIND_IP=127.0.0.3`, port-reset override, `--no-build --pull never`):
  - `infra/data/media` made by `mkdir -p` as a normal user (root here, mode 755): the guide's media check printed `touch: cannot touch '/srv/media/.w': Permission denied`; `storage.put_encrypted('enroll/1/…')` in the backend raised `PermissionError: [Errno 13] Permission denied: '/srv/media/enroll'`; the backend's JSON log formatter writes that text into `docker compose logs backend`. After `chown -R 10001:10001 data/media`: `media ok` from the backend and from the engine, and a 1-byte synthetic object was stored and read back. The UI text "An unexpected error occurred." comes from the backend's generic 500 handler (`core/exceptions.py:88`) via `toApiError`; an accepted photo was not uploaded (that needs a real face);
  - nginx without `--profile ops`: `grafana could not be resolved (3: Host not found)` 5 times in 60 s (about every 11 s); `GET /grafana/` → 502; `GET /api/v1/health` → 200, database and redis ok;
  - ZIP update, exactly as the new guide steps: `docker compose stop` in the old `infra`, copied `.env`, `env/*.env`, the certificates into a fresh copy (tracked + untracked files only), moved `data/`, then `up -d` in the new folder. All containers were recreated with `/srv/media` bound to the new folder, backend and engine healthy, the media check passed, the object stored before the move was readable, and `postgres-data` was reused (migrate ran no upgrade);
  - line-ending check: a clone with `core.autocrlf=true` at `c0ad564` (before `.gitattributes`), then updated to `d55a248`, printed `828`; after `git rm -r --cached . && git reset --hard` it printed `0` and `git status` was clean. This repository prints `0`;
  - `make -n dev` prints the same `up -d --build` command as `make -n dev-up`; `make help` lists `dev`;
  - `docker compose config -q` passes again for the base file, `docker-compose.engine.yml` and base + dev overlay (example env files); services unchanged.
- **Cleanup:** `docker compose down -v` (no facetrack containers, volumes or networks left). Deleted the throwaway `infra/.env`, `infra/env/backend.env`, `infra/env/engine.env`, the dev certificate, the clip and `infra/data/`. The trial admin password and cookie jar were removed from the scratchpad.
- **Not verified:**
  - anything on Windows: Rancher Desktop, WSL `/mnt/d` bind mounts and whether uid 10001 can write to them (the new media check in step 6 shows it on the owner's laptop), Notepad, the PowerShell secret commands (no PowerShell here), Git Bash openssl, `certutil` trust and the webcam;
  - an accepted enrollment photo end to end (needs a real face); the media write path was tested directly in the backend container;
  - building the engine image on the owner's network;
  - the guide's `git rm -r --cached . && git reset --hard` (from the earlier batch);
  - recognition of a real face from a Windows Camera clip (no real faces may be used here; the synthetic clip has none). Steps 8–9 of the guide describe the expected behaviour;
  - the `ops` profile services on a laptop;
  - the CI workflow itself (GitHub Actions cannot run here).

## Notes
- Decisions are recorded as Q57 in `docs/open-questions.md`. The `ops` profile, the stricter healthcheck and the `COMPOSE_FILE` shortcut were not asked for by name. They are dev-overlay-only conveniences and do not change production files.
- Flagged, not changed (outside this task's area):
  - `engine/scripts/sample_video.py`'s docstring still says "`make dev` (looped by MediaMTX)". `make dev` now exists, but it does not loop clips through MediaMTX: the engine reads `file://` clips directly;
  - in `engine/Dockerfile`, the model download layer comes after `COPY engine/app`, so any engine code change downloads the models from huggingface.co again on rebuild (documented in the guide). Moving that step earlier would only change caching;
  - the root `README.md` is stored as UTF-16LE without a BOM (since commit 7a50f4d). Git treats it as binary and GitHub may not render it. This batch kept that encoding and only added a link.
- Frontend files were being changed by another task at the same time. This batch did not touch them.
- Independent review: all five findings were confirmed and fixed (media write permission check, line-ending check instead of a date, `infra/data/` in ZIP updates, the expected nginx Grafana log line, `make dev`).
