# Running FaceTrack on one Windows laptop (development and testing)

This guide runs the whole system on one Windows 11 laptop: the portal, the backend, the database and **one recognition engine**. It is for development and testing only. Production uses separate servers ([`docs/runbook.md`](runbook.md)).

Rules for test machines (CLAUDE.md §1.3, standards/18):
- Use recorded video clips only. Never connect live production cameras.
- Enroll or record only people who agreed in writing (consent).
- Never commit or share face photos, clips, `.env` files or keys.

How to read this guide:
- Run every command in the **Ubuntu terminal** (WSL), unless a step says PowerShell.
- The project lives **inside Ubuntu**, in `~/Ai_Attendence_System` (Windows Explorer: `\\wsl$\Ubuntu\home\<your Ubuntu user>\Ai_Attendence_System`). Do not run it from a Windows drive (`/mnt/d/...`): under Rancher Desktop, Docker does not reliably see files there (seen on the owner's laptop: `not a directory` for `mediamtx.yml`, clips not found, `Permission denied` for photos).
- The `D:` drive is used only to receive the bundle file: `D:\Applications\Atlas\Attendence_System\` is `/mnt/d/Applications/Atlas/Attendence_System/` in Ubuntu.

## 1. What you need

- Windows 11, at least 15 GB free disk space. 16 GB RAM is comfortable; with 8 GB RAM, do step 2.1 first, or WSL can run out of memory and the Ubuntu terminal closes and will not reopen.
- [Rancher Desktop](https://rancherdesktop.io/) and Ubuntu for WSL (Microsoft Store).
- Internet access for the first build (step 6).

## 2. Set up Rancher Desktop (once)

1. Open Rancher Desktop, then **Preferences**:
   - **Container Engine**: choose **dockerd (moby)**.
   - **Kubernetes**: untick **Enable Kubernetes**.
   - **WSL → Integrations**: tick **Ubuntu**.
2. Click **Apply**. Wait until Rancher Desktop says it is running.
3. Open the Ubuntu terminal and check:
   ```bash
   docker version            # must show "Client" and "Server"
   docker compose version
   ```

Use `docker` only from Ubuntu. In PowerShell it fails with `timed out dialing Hyper-V socket`.

### 2.1 Laptops with 8 GB RAM

In PowerShell, give WSL a fixed memory limit plus swap:
```powershell
Set-Content -Path "$env:USERPROFILE\.wslconfig" -Value "[wsl2]`nmemory=4GB`nswap=8GB" -Encoding ascii
```
Then quit Rancher Desktop (tray icon → **Quit**), run `wsl --shutdown`, check that `wsl -l -v` shows every line **Stopped**, and start Rancher Desktop again. In step 4.2 also add `ENGINE_DEV_MEMORY=2g` and `WEB_CONCURRENCY=1` to `infra/.env`.

## 3. Get the code (no GitHub needed)

The office network blocks github.com. IT sends the code as a **git bundle** file (`Ai_Attendence_System.bundle`).

**First time.** Put the bundle file in `D:\Applications\Atlas\Attendence_System\`, then clone it into Ubuntu's own folder:
```bash
git clone -b main /mnt/d/Applications/Atlas/Attendence_System/Ai_Attendence_System.bundle ~/Ai_Attendence_System
```

**Updates.** Replace the bundle file with the new one, then:
```bash
cd ~/Ai_Attendence_System
git pull /mnt/d/Applications/Atlas/Attendence_System/Ai_Attendence_System.bundle main
```

**Moving an existing copy from `D:` into Ubuntu.** The database, photos and clips are in Docker volumes of the project `facetrack`, so they carry over:
```bash
cd /mnt/d/Applications/Atlas/Attendence_System/Ai_Attendence_System/infra && docker compose down
git clone /mnt/d/Applications/Atlas/Attendence_System/Ai_Attendence_System ~/Ai_Attendence_System
cp .env ~/Ai_Attendence_System/infra/ && cp env/*.env ~/Ai_Attendence_System/infra/env/ && cp nginx/certs/*.pem ~/Ai_Attendence_System/infra/nginx/certs/
mkdir -p ~/Ai_Attendence_System/infra/data/videos && cp data/videos/* ~/Ai_Attendence_System/infra/data/videos/
cd ~/Ai_Attendence_System/infra && docker compose up -d
```
Never add `-v` to `docker compose down`: it deletes those volumes.

**ZIP instead of a bundle.** Extract it so that `Ai_Attendence_System` contains `README.md`, `infra`, `backend` and so on. For each update:
1. Stop the system: `docker compose stop` in the old `infra` folder.
2. Copy your `infra/.env`, `infra/env/*.env` and `infra/nginx/certs/` into the new folder.
3. Move your `infra/data/` folder into the new `infra` folder. It holds the encrypted enrollment photos, the snapshots and your test clips. Move it, do not copy it, so that only one copy of this data exists.
4. Continue in the new folder (step 6).

**Line endings (once).** Copies made before `.gitattributes` was added (commit `d55a248`, 4 October 2026, 12:40 Pakistan time) can still have Windows line endings. Check:
```bash
cd ~/Ai_Attendence_System
git ls-files --eol | grep -c 'w/crlf'
```
If it prints `0`, skip the rest of this step. Otherwise run:
```bash
git rm -r --cached . && git reset --hard
```
This rewrites every file with Linux line endings. It throws away your own changes to project files. Your `.env` files are not touched, because git ignores them. Afterwards the check must print `0`.

## 4. Configure (once)

```bash
cd ~/Ai_Attendence_System/infra
cp .env.example .env
cp env/backend.env.example env/backend.env
mkdir -p data/videos
```

Edit the files with `nano .env` in Ubuntu (save: Ctrl+O, Enter; exit: Ctrl+X), or with Notepad in Windows.

### 4.1 Make the secrets

Make a **new value for each secret**. Do not reuse a value. Use hex for all passwords, because they go into connection URLs, and a `/` from base64 breaks them.

**Hex value** (every password, `JWT_SECRET`, `ENGINE_API_TOKEN`). In PowerShell:
```powershell
$b=[byte[]]::new(32); [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); -join ($b | ForEach-Object { $_.ToString('x2') })
```
Or in Ubuntu: `openssl rand -hex 32`

**`ENCRYPTION_KEY`** (base64, 32 bytes). In PowerShell:
```powershell
$b=[byte[]]::new(32); [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b)
```
Or in Ubuntu: `openssl rand -base64 32`

Keep a copy of `ENCRYPTION_KEY` in a safe place. If it is lost, enrolled faces and camera URLs cannot be read any more.

### 4.2 `infra/.env`

| Key | Value on the laptop |
|---|---|
| `SERVER_NAME` | `localhost` |
| `MEDIAMTX_PUBLIC_HOST` | `127.0.0.1` |
| `POSTGRES_PASSWORD`, `ENGINE_DB_PASSWORD`, `REDIS_PASSWORD`, `BACKUP_ENCRYPTION_KEY`, `GRAFANA_ADMIN_PASSWORD` | a different hex value each |

Leave the other lines as they are.

### 4.3 `infra/env/backend.env`

| Key | Value on the laptop |
|---|---|
| `ENVIRONMENT` | `development` |
| `JWT_SECRET` | hex value |
| `ENCRYPTION_KEY` | base64 value |
| `CORS_ORIGINS` | `["https://localhost"]` — must be **exactly** the address in the browser's address bar: `https`, no `/` at the end. If you also open `https://127.0.0.1`, use `["https://localhost","https://127.0.0.1"]`. |
| `PORTAL_BASE_URL` | `https://localhost` |
| `ENGINE_NODES` | `{"node-1": "http://engine:8100"}` |
| `ENGINE_API_TOKEN` | hex value |

Leave the other lines as they are.

### 4.4 `infra/env/engine.env`

The engine needs two values from `env/backend.env`: `ENCRYPTION_KEY` and `ENGINE_API_TOKEN`. This command copies them, so you do not have to type them:
```bash
{ grep '^ENCRYPTION_KEY=' env/backend.env | sed 's/^/ENGINE_/'; grep '^ENGINE_API_TOKEN=' env/backend.env; } | tr -d '\r' > env/engine.env
cut -d= -f1 env/engine.env      # must print ENGINE_ENCRYPTION_KEY and ENGINE_API_TOKEN
```
If you change either value in `env/backend.env` later, run the command again. Everything else the engine needs is set in `infra/docker-compose.dev.yml`.

### 4.5 Include the engine in every `docker compose` command

The engine is defined in `infra/docker-compose.dev.yml`. This line in `infra/.env` makes every `docker compose` command in `infra/` use it:
```bash
printf '\nCOMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml\n' >> .env
docker compose config --services      # the list must include "engine"
```
Without this line, type `docker compose -f docker-compose.yml -f docker-compose.dev.yml` instead of `docker compose` in every command below.

On the laptop, the backup and monitoring services (backup, Prometheus, Alertmanager, Grafana, node-exporter) do not start. They are only needed on servers. To start them anyway, add `--profile ops`. Without them, `docker compose logs nginx` shows `grafana could not be resolved` about every 10 seconds, and https://localhost/grafana/ shows `502 Bad Gateway`. This is expected and does not affect the portal.

## 5. Development certificate (once)

In Ubuntu:
```bash
cd ~/Ai_Attendence_System/infra
sh nginx/gen-dev-cert.sh localhost
```

The browser warns "Your connection isn't private", because you made this certificate yourself. Click **Advanced → Continue to localhost**.

If the webcam does not start on the Enroll tab, or Kaspersky blocks the page, make Windows trust the certificate. First copy it to the D: drive (Ubuntu):
```bash
cp ~/Ai_Attendence_System/infra/nginx/certs/fullchain.pem /mnt/d/Applications/Atlas/Attendence_System/facetrack-dev-cert.pem
```
Then in PowerShell, answer **Yes** to the Windows prompt, and restart the browser (close every window):
```powershell
certutil -user -addstore Root D:\Applications\Atlas\Attendence_System\facetrack-dev-cert.pem
```

## 6. Start

The first build downloads base images and packages from these sites:
- Docker Hub;
- ghcr.io (the `uv` tool);
- pypi.org and files.pythonhosted.org (Python packages);
- registry.npmjs.org (portal);
- huggingface.co (face models).

If the office network blocks any of them, connect the laptop to a mobile hotspot for the build. The engine image is about 3 GB, so the first build can take a long time.

```bash
cd ~/Ai_Attendence_System/infra
docker compose up -d --build
```

Wait about one minute, then check `docker compose ps -a`:
- `migrate` shows `Exited (0)`;
- `postgres`, `redis`, `backend`, `worker`, `engine` and `nginx` show `(healthy)`;
- `scheduler` and `mediamtx` show `Up`.

Check the engine:
```bash
docker compose exec engine curl -s http://localhost:8100/health
```
The answer must contain `"status":"ok"`.

Check that the system can save photos:
```bash
docker compose exec backend sh -c 'touch /srv/media/.w && rm /srv/media/.w && echo media ok'
```
It must print `media ok`. On the laptop, photos and snapshots are kept in a Docker volume (`facetrack_media`), not in a Windows folder, so this works without changing any folder permissions.

Open **https://localhost** in the browser.

If you have `make` (`sudo apt install make`), these do the same from the project folder: `make dev` (start; same as `make dev-up`), `make dev-down`, `make dev-logs S=engine`.

## 7. First admin (once)

```bash
read -rs PW; docker compose run --rm -e SEED_ADMIN_USERNAME=admin -e SEED_ADMIN_EMAIL=you@example.com -e SEED_ADMIN_PASSWORD="$PW" backend python -m app.scripts.seed; unset PW
```
Type the password and press Enter. Nothing shows while you type. The password needs at least 10 characters, with at least one letter and one digit. The command prints `seed complete`. Then sign in at https://localhost as `admin`.

## 8. Enroll an employee

1. **Employees → Add employee.** Fill in **Biometric consent signed on**, but only after the person has signed the consent form. Without it, enrollment is blocked.
2. Open the employee, then the **Enroll** tab. Upload 3 to 10 photos, or take them with the webcam.
   - Exactly one face per photo.
   - The face is at least 112 pixels wide.
   - Sharp, well lit, looking at the camera.
   - JPEG or PNG, up to 5 MB.

   Each photo is accepted or rejected with a reason (for example: no face, more than one face, face too small, too blurry). Enrollment is complete after 3 accepted photos.

## 9. Test recognition with a recorded clip

1. Record a 30 to 60 second clip with the Windows **Camera** app. Record yourself, or a colleague who agreed, walking towards the laptop with the face clearly visible. The app saves MP4 files in `Pictures\Camera Roll`.
2. Copy the clip into `~/Ai_Attendence_System/infra/data/videos/` with a simple name without spaces, for example (replace `<you>` and the file name):
   ```bash
   cp "/mnt/c/Users/<you>/Pictures/Camera Roll/WIN_20261004_16_20_00_Pro.mp4" ~/Ai_Attendence_System/infra/data/videos/test1.mp4
   ```
   Then copy it into the engine (in `infra/`):
   ```bash
   docker compose cp data/videos/. engine:/srv/videos
   docker compose exec engine ls -l /srv/videos
   ```
   The second command must list the clip. The clips stay in the engine's `videos` volume until you delete them; repeat the copy for every new clip.
3. Enroll that person first (step 8).
4. **Cameras → Add camera**:
   - Name: `Test clip`;
   - Location: any;
   - Role: Entry;
   - Engine node: `node-1`;
   - Main stream URL: `file:///srv/videos/test1.mp4`.

   Then save.
5. Within about 30 seconds the camera shows as online, with an FPS value. The clip plays in a loop, in real time. When the face is recognised, the event appears on the Dashboard and in the **Event log**, and the person's check-in appears in **Attendance**.

Notes:
- `file://` cameras work only when `ENVIRONMENT=development` is set in `env/backend.env`. The laptop engine allows them; production engines do not.
- **Live view** does not show file cameras. MediaMTX cannot read files, so this is expected. Live view works with real RTSP cameras.
- A clip of a real person is biometric data. Keep it only on this laptop and delete it after testing. Git ignores `infra/data/` and `.mp4` files.

## 10. Daily use

| Task | Command (in `infra/`) |
|---|---|
| Start (after Rancher Desktop is running) | `docker compose up -d` |
| Stop, keep everything | `docker compose stop` |
| Check | `docker compose ps` |
| Follow logs (Ctrl+C stops following) | `docker compose logs -f --tail 100 engine` (or `backend`, `worker`, `nginx`) |
| After an update (step 3) | `docker compose up -d --build` |
| After editing an env file | `docker compose up -d` (it recreates the changed services) |

- **Never run `docker compose down -v`.** It deletes the database, the enrolled faces and the settings.
- The face models are downloaded only when the engine image is built for the first time, or when `engine/Dockerfile`, `engine/pyproject.toml`, `engine/uv.lock` or the shared `common/` package change. A normal engine code update rebuilds in under a minute without internet access to huggingface.co. If the office network breaks the download with `CERTIFICATE_VERIFY_FAILED` (Kaspersky or another proxy that inspects HTTPS), build on a mobile hotspot.
- The engine uses at most 2 CPUs and 3 GB of memory. To change this, set `ENGINE_DEV_CPUS` and `ENGINE_DEV_MEMORY` in `infra/.env`, then run `docker compose up -d`.

## 11. Troubleshooting

| Problem | What to do |
|---|---|
| `git clone` or `git pull` from GitHub fails | The office network blocks github.com. Use the bundle file from IT (step 3). |
| A container fails with `$'\r': command not found`, `bad interpreter`, `set: Illegal option -`, or `no such file or directory` for a `.sh` file | Windows line endings. Run the line-endings commands in step 3, then `docker compose up -d --build`. If PostgreSQL was first started while the files were broken, also do 11.1. |
| Ubuntu says `docker: command not found` | Start Rancher Desktop. Tick **WSL → Integrations → Ubuntu** and click **Apply**. Close and reopen Ubuntu. If it still fails, run `wsl --shutdown` in PowerShell and start Rancher Desktop again. |
| `Cannot connect to the Docker daemon` | Rancher Desktop is not running yet. Start it and wait until it is ready. |
| PowerShell says `timed out dialing Hyper-V socket` | Do not use docker from PowerShell. Use the Ubuntu terminal. |
| Saving anything in the portal gives 403 or "Request origin is not allowed" | `CORS_ORIGINS` in `env/backend.env` does not match the browser address. Make it exactly that address (step 4.3), then run `docker compose up -d`. |
| "Missing or invalid CSRF token" | Reload the page and sign in again. |
| `docker compose` says `env file .../infra/env/engine.env not found` | Do step 4.4. |
| Enroll says "The recognition engine is unavailable. Please try again shortly." | The engine is not running, or it is not reachable. Check `docker compose ps engine` (must be `healthy`). If `engine` is missing, do step 4.5 and then `docker compose up -d --build`. Check `ENGINE_NODES={"node-1": "http://engine:8100"}` in `env/backend.env`. If you changed `ENGINE_API_TOKEN` or `ENCRYPTION_KEY`, do step 4.4 again, then `docker compose up -d`. |
| The engine restarts again and again, and `docker compose logs engine` shows `password authentication failed for user "facetrack_engine"` | The engine's database role is missing, or it has an old password. See 11.1. |
| The engine build stops at `uv sync` or `download_models.py` with a network error | The network blocks PyPI or huggingface.co. Use a mobile hotspot for the build (step 6). |
| The browser shows a **Kaspersky** page "Visiting a domain with an untrusted certificate" and *I understand the risks and want to continue* does nothing | Trust the development certificate for your Windows user (step 5, `certutil -user -addstore Root ...`), answer **Yes**, close every browser window and open https://localhost again. If Kaspersky still blocks it, ask IT to add `localhost` to Kaspersky's trusted addresses (encrypted connections scan). |
| Saving a camera says "File sources are only allowed in development." | Set `ENVIRONMENT=development` in `env/backend.env`, then run `docker compose up -d`. |
| A file camera stays offline, and `docker compose logs engine` shows `No such file or directory: '/srv/videos/...'` | The clip was not copied into the engine, or the name is different (capital letters matter). Run `docker compose cp data/videos/. engine:/srv/videos`, then check with `docker compose exec engine ls -l /srv/videos`. |
| The clip plays, but nobody is recognised | Check that the person has at least 3 accepted photos. The face in the clip must be large and sharp: walk close to the camera, in good light. Sightings that did not match appear in **Unknown faces**. Do not lower the match threshold to make it work (false matches are worse than misses). |
| Live view of a file camera shows an error | Expected (step 9). |
| The Ubuntu terminal closes by itself during a build or `docker compose up`, and will not open again | WSL ran out of memory. Do step 2.1 (`.wslconfig`), quit Rancher Desktop, `wsl --shutdown`, start Rancher Desktop again. Build the portal with the engine stopped: `docker compose stop engine && docker compose build nginx && docker compose up -d`. |
| `mediamtx` (or another service) fails with `error mounting ... not a directory: Are you trying to mount a directory onto a file` | The project is on a Windows drive (`/mnt/d/...`). Move it into Ubuntu (step 3, *Moving an existing copy*). |
| The browser warns that the connection is not private | Expected with the development certificate (step 5). |
| The media check in step 6 says `Permission denied`, Enroll gives "An unexpected error occurred." with `Permission denied: '/srv/media/...'` in `docker compose logs backend`, or the engine logs `event delivery failed; buffering` with `PermissionError` | The engine is not running with the laptop overlay (step 4.5), so the services use the server-style `MEDIA_DIR` folder instead of the `media` volume. Check `docker compose config --services` lists `engine`, then run `docker compose up -d`. As a one-off repair of a running container: `docker compose exec -u root backend chown -R 10001:10001 /srv/media` (and the same for `engine`). Buffered events are delivered automatically once the engine can write. |
| `docker compose logs nginx` repeats `grafana could not be resolved`, and https://localhost/grafana/ shows `502 Bad Gateway` | Expected on the laptop: Grafana is not started (step 4.5). The portal is not affected. |

### 11.1 Repair the engine's database role

PostgreSQL creates the read-only role `facetrack_engine` only the first time it starts with an empty database. If the setup script was broken then (Windows line endings), or `ENGINE_DB_PASSWORD` was changed later, the engine cannot sign in. Check:
```bash
docker compose exec postgres psql -U facetrack -d facetrack -tAc "SELECT rolname FROM pg_roles WHERE rolname='facetrack_engine'"
```
It must print `facetrack_engine`. To repair it, run these three commands. If the first one says the role does not exist, that is fine.
```bash
docker compose exec postgres psql -U facetrack -d facetrack -c "DROP OWNED BY facetrack_engine" -c "DROP ROLE facetrack_engine"
docker compose exec postgres sh /docker-entrypoint-initdb.d/10-engine-role.sh
docker compose restart engine
```
The role only reads data. Removing and re-creating it does not change any attendance, employee or face data.
