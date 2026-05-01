# Cobweb — DAST Scanning Platform

Multi-tenant Dynamic Application Security Testing (DAST) platform powered by **Nuclei** and **OWASP ZAP**.

> Status: **Phase 0 — Foundations**. See [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md) for the full design.

## Components

| Path | Description |
|---|---|
| `apps/api` | FastAPI backend (auth, scan orchestration, vuln mgmt, audit) |
| `apps/web` | Next.js 15 frontend (dashboard, scan wizard, vuln board) |
| `apps/cli` | `cobweb-cli` for CI/CD pipelines |
| `workers/nuclei-runner` | Nuclei scan worker (containerized) |
| `workers/zap-runner` | OWASP ZAP scan worker (containerized) |
| `deploy/helm/cobweb` | Kubernetes Helm chart |
| `deploy/docker` | Production Dockerfiles |

## Local development

Prerequisites: Docker + Docker Compose, `uv`, Node.js 20+, pnpm. See [`docs/MIGRATION.md`](docs/MIGRATION.md) §1 for install commands on a fresh Ubuntu 24.04 host.

```bash
make bootstrap         # generate env files, start docker stack, install deps, run migrations
make dev-up            # start API, web, nuclei-runner, zap-runner
make register-admin    # create first admin + organization
# open http://<LAN_IP>:3000 in a browser
```

Other targets: `make status`, `make logs`, `make dev-down`, `make clean`.

The bootstrap script auto-detects the host's LAN IP and writes it into `apps/web/.env.local` and the API CORS allow-list. Override with `LAN_IP=… ./scripts/bootstrap.sh`.

There is no migration-time seed admin — the first user is created via `/api/v1/auth/register`, which `scripts/register-admin.sh` calls for you.

## Roles

- **Admin** — org-wide control (users, billing, SSO, audit export)
- **Project Admin** — manages projects, targets, members
- **User** — creates scans, manages vuln state for assigned projects
- **Auditor** — read-only across all projects + audit log access

## Documentation

- [System Architecture](docs/architecture/system-architecture.md)
- [Migration Runbook](docs/MIGRATION.md) — fresh-host bootstrap on Ubuntu 24.04
- [API Reference](docs/api/) (auto-generated OpenAPI)
- [Runbooks](docs/runbooks/)

## License

Proprietary — internal platform.
