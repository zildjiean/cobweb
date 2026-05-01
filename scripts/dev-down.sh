#!/usr/bin/env bash
# Stop all dev processes started by scripts/dev-up.sh.
# Does NOT touch docker compose (data stays). To wipe data: docker compose down -v.

set -euo pipefail

LOG_DIR="${COBWEB_LOG_DIR:-/tmp}"

log() { printf '\033[36m[dev-down]\033[0m %s\n' "$*"; }

stop() {
  local name="$1"
  local pid_file="$LOG_DIR/cobweb-$name.pid"
  [[ -f "$pid_file" ]] || { log "$name: not running"; return; }

  local pid
  pid=$(cat "$pid_file")
  if kill -0 "$pid" 2>/dev/null; then
    log "stopping $name (pid $pid)"
    # Kill the whole process group to catch child python/node.
    kill -TERM -- "-$(ps -o pgid= "$pid" | tr -d ' ')" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    sleep 1
    kill -KILL "$pid" 2>/dev/null || true
  else
    log "$name: pid $pid already gone"
  fi
  rm -f "$pid_file"
}

stop api
stop web
stop nuclei-worker
stop zap-worker

log "done. (docker compose still running — stop with: docker compose down)"
