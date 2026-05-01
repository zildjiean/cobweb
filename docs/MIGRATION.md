# Cobweb — Migration Runbook

**Audience:** the operator (or Claude Code) standing up a fresh Cobweb environment on a new Ubuntu 24.04 host.

**Scope:** this is MVP1, so we **do not** migrate runtime data (users, scans, findings, MinIO artifacts). The destination starts with an empty database and a single freshly-registered admin. Source code is the source of truth — it lives in https://github.com/zildjiean/cobweb.

If you need to preserve data later, see *§Data migration (deferred)* at the bottom.

---

## Topology recap

```
host (Ubuntu 24.04)
├── docker compose stack ................ infra (Postgres / Redis / Rabbit / MinIO / OpenSearch / ZAP)
├── apps/api  (FastAPI, uvicorn :8000) .. host process, uv-managed venv
├── apps/web  (Next.js dev :3000) ....... host process, pnpm
├── workers/nuclei-runner ............... host process, hits docker stack
└── workers/zap-runner .................. host process, hits docker stack
```

All four host processes (api, web, two workers) talk to the docker stack on `localhost`. Browser clients talk to `apps/web` and `apps/api` over the host's **LAN IP** (`hostname -I | awk '{print $1}'`).

---

## 1. Prerequisites (Ubuntu 24.04)

Install once, in this order. Verify each before moving on.

### 1.1 System packages

```bash
sudo apt update
sudo apt install -y \
  curl git build-essential pkg-config \
  ca-certificates gnupg lsb-release \
  openssl jq
```

### 1.2 Docker Engine + Compose plugin

```bash
# official Docker apt repo (required — distro's docker.io is too old)
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# let your user run docker without sudo
sudo usermod -aG docker "$USER"
newgrp docker      # apply group change in current shell

# verify
docker version
docker compose version
```

### 1.3 uv (Python package + project manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# follow the printed instruction to add ~/.local/bin to PATH (or restart shell)

# verify
uv --version
```

### 1.4 Node.js 20 + pnpm

```bash
# Node 20 LTS via NodeSource
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# pnpm via corepack (ships with Node)
sudo corepack enable
corepack prepare pnpm@latest --activate

# verify
node --version            # v20.x
pnpm --version
```

### 1.5 Nuclei (DAST scanner binary)

The Nuclei worker shells out to the `nuclei` binary, so it must be on `$PATH`.

```bash
# Easiest: use the official static binary release
NUCLEI_VERSION="3.3.7"
curl -fsSL "https://github.com/projectdiscovery/nuclei/releases/download/v${NUCLEI_VERSION}/nuclei_${NUCLEI_VERSION}_linux_amd64.zip" -o /tmp/nuclei.zip
sudo unzip -o /tmp/nuclei.zip -d /usr/local/bin/ nuclei
sudo chmod +x /usr/local/bin/nuclei
rm /tmp/nuclei.zip

# fetch templates (~5 min on first run)
nuclei -update-templates

# verify
nuclei -version
```

> ZAP runs **inside docker compose** (no host install needed) — it's already in the docker-compose.yml.

---

## 2. Clone the repository

```bash
cd ~                       # or wherever you want the workspace
git clone https://github.com/zildjiean/cobweb.git
cd cobweb
```

---

## 3. Bootstrap

```bash
./scripts/bootstrap.sh
```

What it does:
- detects your LAN IP (override with `LAN_IP=… ./scripts/bootstrap.sh`)
- generates fresh `apps/api/.env` with random `COBWEB_SECRET_KEY` + `COBWEB_WORKER_TOKEN`
- generates `apps/web/.env.local` pointing the browser at `http://<LAN_IP>:8000`
- `docker compose up -d` for infra
- waits for Postgres healthcheck
- `uv sync` + `alembic upgrade head` for the API
- `pnpm install` for the web
- creates per-worker venvs (`workers/nuclei-runner/.venv`, `workers/zap-runner/.venv`) and installs their requirements

It is idempotent. Re-run any time. Pass `--force` to regenerate env files (rotates secrets — only do this if you know what you're doing).

Verify:

```bash
docker compose ps                       # all services Up + healthy except minio-init (Exited 0 is OK)
ls -la apps/api/.env apps/web/.env.local
grep -c '^COBWEB_SECRET_KEY=[a-f0-9]\{64\}$' apps/api/.env   # → 1
```

---

## 4. Start the dev processes

```bash
./scripts/dev-up.sh
```

This starts (in background, logs to `/tmp/cobweb-*.log`):
- API (uvicorn :8000)
- web (Next.js :3000)
- nuclei-runner (consumes RabbitMQ)
- zap-runner (consumes RabbitMQ)

Verify:

```bash
curl -fsS http://localhost:8000/health                    # → {"status":"ok"}
curl -fsS http://localhost:3000/login -o /dev/null && echo "web ok"
ls /tmp/cobweb-*.pid                                      # → 4 pid files
tail -n 5 /tmp/cobweb-api.log                             # uvicorn ready line
```

If something didn't start, check the matching log:

```bash
tail -50 /tmp/cobweb-api.log
tail -50 /tmp/cobweb-web.log
tail -50 /tmp/cobweb-nuclei-worker.log
tail -50 /tmp/cobweb-zap-worker.log
```

Stop everything with `./scripts/dev-down.sh`. Add `docker compose down` to also stop infra.

---

## 5. Create the first admin user

```bash
./scripts/register-admin.sh
```

Interactive prompts ask for email, full name, org name, password. Or set them via env:

```bash
EMAIL=admin@cobweb.local FULL_NAME='Cobweb Admin' \
  ORG_NAME='Cobweb Local' PASSWORD='ChangeMe!2026' \
  ./scripts/register-admin.sh
```

> The API enforces password complexity. If you see `422 Unprocessable Entity`, your password is too weak — try ≥12 chars, mixed case, a digit, a symbol.

Verify by logging in:

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@cobweb.local","password":"ChangeMe!2026"}' \
  | jq '.access_token != null'        # → true
```

---

## 6. End-to-end sanity check

1. Open the UI in a browser: **`http://<LAN_IP>:3000`** — login with the admin you just created.
2. Create a project + target (any safe URL — `https://pentest-ground.com:4280/` is the project's default test target).
3. Trigger a Nuclei *quick* scan. Within ~30 s the scan should leave `queued`, you should see findings stream in, and the progress bar should advance. Completes in 3–10 min.
4. Trigger a ZAP *high* scan against the same target. Spider phase ~2–5 min, active scan ~20–40 min depending on host CPU. Findings stream live.

If both engines complete and you see findings in the UI: migration is done.

---

## 7. Tuning ZAP for a beefy host

The committed `docker-compose.yml` caps ZAP at **`mem_limit: 768m` + `_JAVA_OPTIONS: -Xmx512m`**. That was a workaround for a tight 4 GB dev box where ZAP would OOMKill itself during full active scans (browser-based plugins like DomXss spawn headless Chromium which alone wants ~200 MB).

On the new host (≥8 GB RAM), bump it back to comfortable defaults:

```yaml
# docker-compose.yml — zap service
    environment:
      _JAVA_OPTIONS: "-Xmx2g"        # was 512m
    mem_limit: 3g                    # was 768m
```

Then `docker compose up -d zap` to apply. Verify:

```bash
docker logs cobweb-zap-1 2>&1 | grep -E "_JAVA_OPTIONS|maxMemory" | head -3
docker inspect cobweb-zap-1 --format='{{.HostConfig.Memory}}'   # 3221225472
```

---

## 8. Tuning checklist (optional, do once stable)

- [ ] Bind docker-compose ports to `127.0.0.1` only, in front of a reverse proxy (NGINX / Caddy with TLS) — current dev defaults bind on `0.0.0.0`, which exposes Postgres/Redis/RabbitMQ to the LAN.
- [ ] Rotate `COBWEB_SECRET_KEY` and `COBWEB_WORKER_TOKEN` — `bootstrap.sh --force` does this if you also re-run alembic and re-issue tokens, but **do not** rotate after users start logging in (it invalidates every session).
- [ ] Change Postgres + MinIO + RabbitMQ default passwords (currently `cobweb / cobweb` and `cobweb / cobwebsecret`). Update both `docker-compose.yml` and `apps/api/.env`.
- [ ] Set `COBWEB_DEV_SKIP_TARGET_VERIFICATION=false` so users must prove ownership before they can scan a target (DNS TXT / file upload / meta tag — see scope rules in `apps/api/cobweb/api/v1/targets.py`).
- [ ] Set `COBWEB_DEBUG=false`.
- [ ] Add a `restart: unless-stopped` policy to all services in docker-compose so the stack survives reboots.
- [ ] Pin docker images by digest (current tags use `latest`).

---

## 9. Common issues

| Symptom | Cause | Fix |
|---|---|---|
| `connection refused` on `:8000` from the browser, but `curl localhost:8000` works | `apps/web/.env.local` still has `localhost` and you're browsing from a different machine | Set `NEXT_PUBLIC_API_BASE=http://<LAN_IP>:8000` and restart `pnpm dev` |
| Login returns `403 CORS` in DevTools console | The web origin isn't in `COBWEB_CORS_ALLOWED_ORIGINS_RAW` | Add it (`http://<LAN_IP>:3000`) and restart the API |
| Worker logs `ZAP ascan unresponsive after 4 retries` | ZAP container OOMKilled mid-scan | See §7 — bump `mem_limit` and `_JAVA_OPTIONS` |
| `alembic upgrade head` fails with `connection refused` | Postgres healthcheck hasn't passed yet | `docker compose ps`, wait for `healthy`, retry |
| `pnpm install` fails on `cpu` requirement | Pre-Node 20 host | `node -v` should be ≥ 20 — re-do §1.4 |
| `uv sync` complains about Python 3.12 | uv hasn't pulled Python yet | `uv python install 3.12 && uv sync` |

---

## 10. Data migration (deferred — for when MVP1 graduates)

When you eventually need to move users/scans/findings/artifacts off this host:

```bash
# on source
docker exec cobweb-postgres-1 pg_dump -U cobweb cobweb | gzip > cobweb.sql.gz
docker run --rm --network cobweb_default \
  -v "$PWD:/out" minio/mc:latest -- \
  mirror local/cobweb-artifacts /out/minio-artifacts/

# scp cobweb.sql.gz minio-artifacts/ → destination

# on destination, after bootstrap.sh
gunzip -c cobweb.sql.gz | docker exec -i cobweb-postgres-1 psql -U cobweb cobweb
docker run --rm --network cobweb_default -v "$PWD:/in" minio/mc:latest -- \
  mirror /in/minio-artifacts/ local/cobweb-artifacts
```

OpenSearch audit logs can be re-indexed via the snapshot/restore API — defer until you actually need them.

---

## 11. Quick reference

```bash
# infra
docker compose up -d                 # start
docker compose down                  # stop (data preserved in volumes)
docker compose down -v               # stop AND wipe volumes ⚠️

# host processes
./scripts/dev-up.sh                  # start api + web + workers
./scripts/dev-down.sh                # stop them
tail -f /tmp/cobweb-*.log            # watch all logs

# admin
./scripts/register-admin.sh          # create first user

# rebuild env files
./scripts/bootstrap.sh --force       # ⚠️ rotates secrets
```
