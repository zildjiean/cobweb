#!/usr/bin/env bash
# Start the local dev stack: API, web, Nuclei worker, ZAP worker.
# Run after scripts/bootstrap.sh has succeeded once.
#
# Logs go to /tmp/cobweb-*.log. PIDs to /tmp/cobweb-*.pid.
# Stop everything with scripts/dev-down.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LOG_DIR="${COBWEB_LOG_DIR:-/tmp}"
mkdir -p "$LOG_DIR"

log() { printf '\033[36m[dev-up]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[dev-up] %s\033[0m\n' "$*" >&2; exit 1; }

[[ -f apps/api/.env ]]       || die "apps/api/.env missing — run scripts/bootstrap.sh"
[[ -f apps/web/.env.local ]] || die "apps/web/.env.local missing — run scripts/bootstrap.sh"

start() {
  local name="$1" cwd="$2" cmd="$3"
  local pid_file="$LOG_DIR/cobweb-$name.pid"
  local log_file="$LOG_DIR/cobweb-$name.log"

  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    log "$name already running (pid $(cat "$pid_file"))"
    return
  fi

  log "starting $name → $log_file"
  ( cd "$cwd" && nohup bash -c "$cmd" >"$log_file" 2>&1 & echo $! > "$pid_file" )
  disown 2>/dev/null || true
}

# Make sure docker-compose infra is up first.
log "ensuring infra is running…"
docker compose up -d >/dev/null

# Pull WORKER_TOKEN out of apps/api/.env so workers authenticate to the API.
WORKER_TOKEN=$(grep '^COBWEB_WORKER_TOKEN=' apps/api/.env | cut -d= -f2-)
[[ -n "$WORKER_TOKEN" ]] || die "COBWEB_WORKER_TOKEN missing from apps/api/.env"

# ZAP API key is hard-coded in docker-compose.yml's zap service command.
ZAP_KEY="cobweb-zap-dev-key"

# Common env passed to both workers.
WORKER_ENV="COBWEB_API_BASE=http://localhost:8000 COBWEB_WORKER_TOKEN=$WORKER_TOKEN"

start api apps/api 'uv run uvicorn cobweb.main:app --host 0.0.0.0 --port 8000'
start web apps/web 'pnpm dev'
start nuclei-worker workers/nuclei-runner \
  "$WORKER_ENV .venv/bin/python -u runner.py"
start zap-worker workers/zap-runner \
  "$WORKER_ENV COBWEB_ZAP_HOST=http://localhost:8090 COBWEB_ZAP_APIKEY=$ZAP_KEY .venv/bin/python -u runner.py"

log "all started. Tail logs with: tail -f $LOG_DIR/cobweb-*.log"
log "stop with: scripts/dev-down.sh"
