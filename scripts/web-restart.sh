#!/usr/bin/env bash
# Rebuild apps/web and restart it in production mode (`next start`).
# Used by `make web-restart` and `make ship`.
#
# Logs go to /tmp/cobweb-web.log, pid to /tmp/cobweb-web.pid.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LOG_DIR="${COBWEB_LOG_DIR:-/tmp}"
PID_FILE="$LOG_DIR/cobweb-web.pid"
LOG_FILE="$LOG_DIR/cobweb-web.log"

log() { printf '\033[36m[web-restart]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[web-restart] %s\033[0m\n' "$*" >&2; exit 1; }

log "building apps/web…"
( cd apps/web && pnpm build )

log "stopping any running web process…"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  kill "$(cat "$PID_FILE")" || true
fi
pkill -f "next start -p 3000" 2>/dev/null || true
pkill -f "next-server"        2>/dev/null || true
sleep 1

if ss -tlnp 2>/dev/null | grep -q ':3000\b'; then
  die "port 3000 still in use after stop — investigate manually"
fi

log "starting web in production mode → $LOG_FILE"
cd apps/web
nohup bash -c 'pnpm start' >"$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"
disown
cd "$REPO_ROOT"

sleep 3
if kill -0 "$NEW_PID" 2>/dev/null; then
  log "web is running (pid $NEW_PID) → http://localhost:3000"
else
  die "web failed to start — check $LOG_FILE"
fi
