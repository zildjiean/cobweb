#!/usr/bin/env bash
# Cobweb — first-time setup on a fresh machine.
#
# What it does (idempotent):
#   1. Verify host prerequisites (docker, docker compose, uv, node, pnpm).
#   2. Create apps/api/.env and apps/web/.env.local from examples (only if missing).
#   3. Auto-detect LAN IP and inject it into both env files.
#   4. Generate fresh secrets for COBWEB_SECRET_KEY and COBWEB_WORKER_TOKEN.
#   5. docker compose up -d to bring up Postgres/Redis/Rabbit/MinIO/OpenSearch/ZAP.
#   6. uv sync inside apps/api, alembic upgrade head.
#   7. pnpm install inside apps/web.
#
# Re-runnable: skips any step that's already done. Pass --force to overwrite env files.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

log() { printf '\033[36m[bootstrap]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[bootstrap]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[31m[bootstrap] %s\033[0m\n' "$*" >&2; exit 1; }

# ---- 1. prerequisites -------------------------------------------------------

log "checking prerequisites…"
need() { command -v "$1" >/dev/null 2>&1 || die "missing: $1 (see docs/MIGRATION.md for install)"; }
need docker
need uv
need node
need pnpm
need nuclei  # Nuclei worker shells out to the `nuclei` binary
docker compose version >/dev/null 2>&1 || die "docker compose plugin not installed"

NODE_MAJOR=$(node -v | sed -E 's/^v([0-9]+).*/\1/')
[[ "$NODE_MAJOR" -ge 20 ]] || die "node >=20 required (have $(node -v))"

PY_VER=$(uv python find 2>/dev/null | xargs -r basename || true)
[[ -n "$PY_VER" ]] || warn "uv hasn't picked a Python yet — first 'uv sync' will install one"

# ---- 2. detect LAN IP -------------------------------------------------------

# Prefer first non-loopback, non-docker IPv4. Fall back to localhost.
detect_lan_ip() {
  local ip
  ip=$(hostname -I 2>/dev/null | awk '{
    for (i=1; i<=NF; i++) {
      if ($i ~ /^127\./) continue
      if ($i ~ /^172\.(1[7-9]|2[0-9]|3[0-1])\./) continue  # docker bridges
      print $i; exit
    }
  }')
  echo "${ip:-127.0.0.1}"
}

LAN_IP="${LAN_IP:-$(detect_lan_ip)}"
log "detected LAN IP: $LAN_IP (override with: LAN_IP=x.y.z.w $0)"

# ---- 3. env files -----------------------------------------------------------

# apps/api/.env
API_ENV="apps/api/.env"
if [[ -f "$API_ENV" && "$FORCE" -eq 0 ]]; then
  log "$API_ENV exists — skip (use --force to regenerate)"
else
  log "writing $API_ENV"
  SECRET_KEY=$(openssl rand -hex 32)
  WORKER_TOKEN=$(openssl rand -hex 32)
  awk -v sk="$SECRET_KEY" -v wt="$WORKER_TOKEN" -v ip="$LAN_IP" '
    /^COBWEB_SECRET_KEY=/   { print "COBWEB_SECRET_KEY=" sk; next }
    /^COBWEB_WORKER_TOKEN=/ { print "COBWEB_WORKER_TOKEN=" wt; next }
    /^COBWEB_CORS_ALLOWED_ORIGINS_RAW=/ {
      print "COBWEB_CORS_ALLOWED_ORIGINS_RAW=http://localhost:3000,http://" ip ":3000"
      next
    }
    { print }
  ' "$API_ENV.example" > "$API_ENV"
  chmod 600 "$API_ENV"
fi

# apps/web/.env.local
# Default: leave NEXT_PUBLIC_API_BASE commented out so apps/web/lib/api.ts
# derives the API base from window.location.hostname at runtime — that lets
# the same build answer on multiple IPs / NAT paths without rebuilding.
# Uncomment / set NEXT_PUBLIC_API_BASE only if the API lives on a different
# host than the web (cross-origin deploy).
WEB_ENV="apps/web/.env.local"
if [[ -f "$WEB_ENV" && "$FORCE" -eq 0 ]]; then
  log "$WEB_ENV exists — skip (use --force to regenerate)"
else
  log "writing $WEB_ENV"
  cat >"$WEB_ENV" <<EOF
# Web runtime config.
# Default: api.ts derives the API base from window.location.hostname at
# runtime so the same build works on every IP / NAT path that reaches it.
# Set this only if the API host differs from the web host:
# NEXT_PUBLIC_API_BASE=http://${LAN_IP}:8000
EOF
fi

# ---- 4. docker compose ------------------------------------------------------

log "starting infra (docker compose up -d)…"
docker compose up -d

log "waiting for postgres healthcheck…"
deadline=$((SECONDS + 60))
until docker compose ps postgres --format json 2>/dev/null | grep -q '"Health":"healthy"'; do
  (( SECONDS > deadline )) && die "postgres didn't become healthy in 60s"
  sleep 2
done

# ---- 5. python deps + migrations -------------------------------------------

log "installing API deps (uv sync)…"
( cd apps/api && uv sync )

log "running alembic migrations…"
( cd apps/api && uv run alembic upgrade head )

# ---- 6. node deps -----------------------------------------------------------

log "installing web deps (pnpm install)…"
( cd apps/web && pnpm install --frozen-lockfile )

# ---- 7. worker venvs --------------------------------------------------------

setup_worker() {
  local dir="$1"
  log "preparing worker venv: $dir"
  ( cd "$dir" && {
      [[ -d .venv ]] || uv venv .venv
      uv pip install --python .venv/bin/python -r requirements.txt
  } )
}

setup_worker workers/nuclei-runner
setup_worker workers/zap-runner

# ---- done -------------------------------------------------------------------

cat <<EOF

[1;32m✓ bootstrap complete[0m

Next steps:
  1. Start the dev processes:        scripts/dev-up.sh
  2. Create the first admin user:    scripts/register-admin.sh
  3. Open the UI:                    http://${LAN_IP}:3000

Generated env files:
  apps/api/.env         (secrets — do not commit)
  apps/web/.env.local   (LAN-specific API base — do not commit)

ZAP is running with mem_limit=768m by default. On a beefier host, bump it in
docker-compose.yml (see docs/MIGRATION.md → "Tuning ZAP").
EOF
