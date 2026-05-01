#!/usr/bin/env bash
# Register the first admin + organization via the public /auth/register endpoint.
# Run once after dev-up.sh. Idempotent: re-running with the same email is a no-op
# (the API returns 409 Conflict and we treat that as success).
#
# Usage:
#   scripts/register-admin.sh                         # interactive prompts
#   EMAIL=… PASSWORD=… ORG_NAME=… scripts/register-admin.sh

set -euo pipefail

API_BASE="${COBWEB_API_BASE:-http://localhost:8000}"

prompt() {
  local var="$1" label="$2" default="${3:-}"
  if [[ -z "${!var:-}" ]]; then
    if [[ -n "$default" ]]; then
      read -rp "$label [$default]: " input
      printf -v "$var" '%s' "${input:-$default}"
    else
      read -rp "$label: " input
      printf -v "$var" '%s' "$input"
    fi
  fi
}

prompt EMAIL     "Admin email"            "admin@cobweb.local"
prompt FULL_NAME "Full name"              "Cobweb Admin"
prompt ORG_NAME  "Organization name"      "Cobweb Local"
if [[ -z "${PASSWORD:-}" ]]; then
  read -rsp "Password (min 12 chars, mixed case + digit): " PASSWORD; echo
fi

payload=$(printf '{"email":"%s","password":"%s","full_name":"%s","org_name":"%s"}' \
  "$EMAIL" "$PASSWORD" "$FULL_NAME" "$ORG_NAME")

http_code=$(curl -s -o /tmp/cobweb-register.out -w '%{http_code}' \
  -X POST "$API_BASE/api/v1/auth/register" \
  -H 'content-type: application/json' \
  -d "$payload")

case "$http_code" in
  201)
    echo "✓ created admin '$EMAIL' for org '$ORG_NAME'"
    ;;
  409)
    echo "→ '$EMAIL' already exists — nothing to do"
    ;;
  *)
    echo "✗ register failed (HTTP $http_code):" >&2
    cat /tmp/cobweb-register.out >&2; echo >&2
    exit 1
    ;;
esac
