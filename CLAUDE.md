# Notes for Claude

Welcome. This file is your jump-start so you can be useful in this repo on day one. Read it whole, then dive in.

---

## What Cobweb is

Multi-tenant DAST (Dynamic Application Security Testing) platform. Users register an org, point it at a target URL, pick a profile (`quick` / `high` / `full` / `custom`), and the platform runs **Nuclei** + **OWASP ZAP** against the target, streaming findings into a UI in real time. Goal: a self-hosted alternative to Rapid7 InsightAppSec / Acunetix where the org owns its templates and workflow.

**Status:** MVP1. Phase 0–2 of the architecture doc are done; Phase 3+ (integrations, SSO, compliance reports) is not. See `docs/architecture/system-architecture.md` for the full design and `README.md` for the component map.

---

## How to run it

`docs/MIGRATION.md` has the full bootstrap recipe for a fresh Ubuntu 24.04 host. The short version:

```bash
make bootstrap         # idempotent first-time setup
make dev-up            # start API + web + nuclei-worker + zap-worker (logs in /tmp/cobweb-*.log)
make register-admin    # create the first user via /auth/register
make status            # see what's running
```

Both API and web run as **host processes** (not in docker). Only the data plane (Postgres / Redis / RabbitMQ / MinIO / OpenSearch / ZAP) lives in `docker-compose.yml`. Workers also run on the host and `.venv/bin/python` against per-worker requirements.txt.

---

## Code map (where things live)

| Concern | Path |
|---|---|
| FastAPI app factory + middleware | `apps/api/cobweb/main.py` |
| Auth (login, register, MFA, OIDC) | `apps/api/cobweb/api/v1/auth.py` |
| RBAC permission matrix | `apps/api/cobweb/core/rbac.py` |
| Scan orchestration + worker probes | `apps/api/cobweb/api/v1/scans.py` |
| SQLAlchemy 2.0 async models | `apps/api/cobweb/models/*.py` |
| Pydantic v2 schemas | `apps/api/cobweb/schemas/*.py` |
| Alembic migrations | `apps/api/alembic/versions/000N_*.py` |
| Settings (env-driven) | `apps/api/cobweb/core/settings.py` |
| Frontend API client (the localhost-fallback bug source) | `apps/web/lib/api.ts` |
| Frontend route groups | `apps/web/app/(auth)`, `apps/web/app/(dashboard)` |
| Reusable UI components | `apps/web/components/ui/*.tsx` |
| Release notes copy + version | `apps/web/lib/release-notes.ts` |
| Nuclei worker (subprocess, stream JSONL) | `workers/nuclei-runner/runner.py` |
| ZAP worker (REST API client, alert dedupe) | `workers/zap-runner/runner.py` |

---

## Conventions to follow

- **Backend:** SQLAlchemy 2.0 *async* style (`AsyncSession`, `select(...).where(...)`), Pydantic v2 strict, FastAPI dependencies for DB session + current user. No sync DB code in routes.
- **Auth:** access tokens in `Authorization: Bearer …` header, refresh tokens not yet in cookies. JWT claims include `org_id` and `role` — read them via `Depends(get_current_user)` which returns `CurrentUser` (already includes role context).
- **Migrations:** every schema change is an alembic revision. Don't `metadata.create_all` outside of tests. Filenames are `000N_short_description.py`, sequential.
- **RBAC:** check permissions with `require(role, "permission:string")` from `core/rbac.py`. Don't gate by role enum directly — gate by permission string. New endpoints must add their permission to the matrix.
- **Workers:** must include the `COBWEB_WORKER_TOKEN` header on every API call (the API verifies via `require_worker_token`). The `/scans/{id}/_worker/active` probe returns 410 GONE when the scan was cancelled — workers use this for cancel detection.
- **Frontend:** TanStack Query for server state (not SWR, not Redux). Tailwind v3 (not v4). lucide-react for icons. ConfirmDialog (`components/ui/ConfirmDialog.tsx`) replaces every `window.confirm`.
- **Logs:** loguru on the backend, browser console on the frontend. Backend log file at `/tmp/cobweb-api.log` when started via `dev-up.sh`.
- **No emoji in code or commits** unless the user asks.
- **No new files unless asked.** Prefer editing.

---

## Gotchas (lessons that already cost us time)

1. **`NEXT_PUBLIC_API_BASE` defaults to localhost.** If a user browses from a different device than the dev box, every API call hits *their* localhost, not the server. Symptoms: "login failed" but no `/auth/login` request in the API log. Fix: `apps/web/.env.local` must use the host's LAN IP. `bootstrap.sh` does this automatically.

2. **Postgres CORS allow-list.** The API's `COBWEB_CORS_ALLOWED_ORIGINS_RAW` must contain the exact origin (`http://<LAN_IP>:3000`) the browser sends. `bootstrap.sh` writes both `localhost:3000` and the LAN IP variant.

3. **ZAP container OOMKills under load.** Browser-based plugins (DomXss, etc.) spawn headless Chromium per scan thread (~200 MB each). On a 4 GB host, `mem_limit: 768m` was barely enough for `quick`, and **always** OOMs on `high`/`full`. The committed default is 768m for the small dev box — **bump to ≥ 2 GB on a beefier host** (see `docs/MIGRATION.md` §7). Symptom: worker logs `ZAP ascan unresponsive after 4 retries`. Confirm with `docker inspect cobweb-zap-1 --format='{{.State.OOMKilled}}'`.

4. **`_JAVA_OPTIONS` overrides `JAVA_OPTS` in the ZAP image.** `zap.sh` ignores `JAVA_OPTS` and computes its own `-Xmx` from container memory. Use `_JAVA_OPTIONS` (read directly by the JVM) to override `-Xmx`.

5. **Stale ZAP alerts cross scan boundaries.** ZAP keeps its alert table across active scans; a fresh scan would re-stream all alerts from the previous run as "new" findings. The runner snapshots `_alert_key()` → set before spider, then filters during streaming. Don't remove this — it costs hundreds of phantom findings per scan.

6. **Cancel is cooperative.** `POST /scans/{id}/cancel` flips DB status to `cancelled`; the worker discovers it via the `/_worker/active` probe (HTTP 410) on its next progress tick (every ~3 s). The worker then SIGTERMs the nuclei subprocess or `ascan_stop`s ZAP. There is **no** way to forcibly kill a worker mid-call from the API — the probe interval is the worst-case latency.

7. **`bootstrap.sh --force` rotates secrets.** That invalidates every active session and worker token. Don't run it on a live system unless you mean it.

8. **First user is created via `/auth/register`**, not seeded by migration. The README used to claim a default `admin@cobweb.local` exists — that was wrong, and is now removed. `scripts/register-admin.sh` is the canonical way.

9. **Workers each have their own venv.** `workers/{nuclei,zap}-runner/.venv` (uv-managed), not the API's venv. `dev-up.sh` invokes `.venv/bin/python -u runner.py`. If you rename a dep, run `bootstrap.sh` to re-sync.

10. **`nuclei` is a host binary**, not packaged. Bootstrap checks `command -v nuclei`. See `docs/MIGRATION.md` §1.5 for install.

---

## Architectural decisions worth knowing

- **Modular monolith for now**, not microservices. Routes are split per domain (`apps/api/cobweb/api/v1/{auth,scans,vulnerabilities,…}.py`) and services likewise. Splitting a service out is a future move when load actually demands it.
- **RabbitMQ for scan jobs**, not Redis or Postgres-as-queue. Quorum queues planned but currently default queues. DLQ not yet wired — failed jobs just exit non-zero and the API marks the scan failed via worker status PUT.
- **MinIO for artifacts** (raw nuclei JSONL, ZAP report.xml, generated PDFs). Bucket `cobweb-artifacts` created by the `minio-init` one-shot service in `docker-compose.yml`. Server-side encryption not yet enabled — TODO for prod.
- **OpenSearch for audit log + future full-text search.** The audit middleware writes both to Postgres `audit_logs` (durable) and to OpenSearch (queryable). If OpenSearch is down, Postgres write still succeeds.
- **Tailwind v3, not v4.** v4 was released but we haven't migrated. Don't use v4-only syntax.

---

## Working with the user

- The user reads/writes Thai fluently. Replying in Thai is fine and often preferred. Code, commit messages, and identifiers stay in English.
- Default to **terse**. The user reads the diff — don't summarize what you just changed unless asked.
- For non-trivial changes, **propose a plan first** (a few bullets, the main tradeoff) and wait for confirmation before writing code. Direct asks like "fix this bug" don't need a plan; "add feature X" does.
- The user's dev box is at LAN IP `192.168.0.144`; they often browse from another device. See gotcha #1.
- For destructive or remote-affecting actions (force push, dropping tables, sending external requests, posting to GitHub/Slack), **always confirm before doing**. A previous approval doesn't carry forward.

---

## Recent context (as of initial commit, 2026-05-01)

- Version 0.1.0 just shipped: live findings stream during scans, smooth time-based progress bars with ETA, ConfirmDialog replacing window.confirm, scan cancel + delete, bulk-delete findings, megaphone release-notes bell with red-dot indicator.
- Phase 1 + 2 of the roadmap are done (Nuclei + ZAP workers, vuln lifecycle stub, audit log). Phase 3+ untouched.
- The dev box is RAM-tight (4 GB total). The committed ZAP `mem_limit: 768m` reflects that — see gotcha #3 before debugging "ZAP ascan unresponsive".
- A new Ubuntu 24.04 host with more RAM is incoming; this repo's portability scaffolding (`scripts/`, `docs/MIGRATION.md`, this file) is for that migration.

---

## When in doubt

- Read the code. SQLAlchemy models and FastAPI routes are short and self-explanatory.
- For "is this safe to run?" — check the Makefile target's underlying script. Anything destructive is annotated.
- For lessons not in this file — check `docs/architecture/system-architecture.md` for design rationale, or git log for the WHY behind a recent change.
