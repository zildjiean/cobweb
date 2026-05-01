# Cobweb — DAST Scanning Platform: System Architecture

## Context

**ปัญหา/ความต้องการ:** องค์กรต้องการแพลตฟอร์ม DAST (Dynamic Application Security Testing) แบบ self-service ที่ทีม Dev / AppSec / Auditor ใช้ scan website เพื่อหา vulnerability ได้เอง โดยใช้ engine ที่เป็น industry-standard (Nuclei + OWASP ZAP) และต้องเชื่อม CI/CD pipeline ได้เพื่อ shift-left security

**ทำไมต้องสร้าง Cobweb (ไม่ใช้ตัวเชิงพาณิชย์อย่าง Rapid7/Acunetix):** ต้องการ control template/signature เอง, customize workflow ให้ตรงกับ vulnerability management process ภายใน, และไม่ต้องผูกกับ vendor

**ผลลัพธ์ที่คาดหวัง:** Multi-tenant SaaS platform ที่
- ทีม dev สั่งสแกนได้ผ่าน UI หรือ API จาก CI/CD
- เปรียบเทียบผลสแกนข้ามครั้ง (regression detection)
- บริหาร vulnerability lifecycle (triage → fix → verify)
- ส่งออก compliance report (PCI-DSS, OWASP Top 10, ISO 27001)
- Audit ทุก action เพื่อตรวจสอบย้อนหลัง

---

## Decisions (จาก Q&A)

| ด้าน | เลือก |
|---|---|
| Backend | **Python (FastAPI)** — async, ecosystem ด้าน security ดี, integrate ZAP/Nuclei ง่าย |
| Frontend | **Next.js 15 + TypeScript + shadcn/ui + Tailwind** — ทำ UX แบบ Rapid7/Acunetix ได้ |
| Tenancy | **Multi-tenant SaaS** |
| Worker Model | **Shared scanner pool + dedicated egress gateway ต่อ tenant** |
| Object Storage | **MinIO (S3-compatible, self-hosted)** |
| Auth | Local + MFA, SSO (SAML 2.0 / OIDC), API Keys |
| Integrations | Jira/GitHub/GitLab Issues, Slack/Teams/Email/Webhook, Compliance reports, SIEM |

---

## High-Level Architecture

```
                   ┌─────────────────────────────────────────────┐
                   │  Users (Browser) / CI/CD Pipelines / 3rd-party
                   └───────────────┬─────────────────────────────┘
                                   │ HTTPS
                          ┌────────▼─────────┐
                          │  Ingress (NGINX/Traefik) + WAF
                          └────────┬─────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
          ┌──────────┐      ┌──────────────┐    ┌────────────┐
          │ Frontend │      │  API Gateway │    │  Public API│
          │ Next.js  │      │  (FastAPI)   │    │ (CI/CD,3P) │
          └──────────┘      └──────┬───────┘    └─────┬──────┘
                                   │                  │
                ┌──────────────────┼──────────────────┘
                ▼                  ▼
        ╔═══════════════════════════════════════════════════╗
        ║              CORE SERVICES (FastAPI)              ║
        ║  ┌────────┐ ┌────────┐ ┌─────────┐ ┌───────────┐ ║
        ║  │ Auth   │ │Project │ │  Scan   │ │ Vuln Mgmt │ ║
        ║  │  IdP   │ │ /Asset │ │ Orchestr│ │           │ ║
        ║  └────────┘ └────────┘ └────┬────┘ └─────┬─────┘ ║
        ║  ┌────────┐ ┌────────┐ ┌────▼────┐ ┌─────▼─────┐ ║
        ║  │Notify  │ │Report  │ │Template │ │  Audit    │ ║
        ║  │        │ │        │ │ Updater │ │   Log     │ ║
        ║  └────────┘ └────────┘ └─────────┘ └───────────┘ ║
        ╚═══════════════════════════════════════════════════╝
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
        ┌────────────┐ ┌────────────┐ ┌────────────┐
        │  RabbitMQ  │ │   Redis    │ │ PostgreSQL │
        │ (Job queue)│ │ (cache,    │ │ + Timescale│
        │            │ │  rate-lim) │ │            │
        └─────┬──────┘ └────────────┘ └────────────┘
              │
              │ scan jobs                    ┌──────────────┐
              ▼                              │ OpenSearch   │
   ┌────────────────────────────┐            │ (audit/find) │
   │  K8s Job Controller        │            └──────────────┘
   │  (spawn ephemeral scanners)│            ┌──────────────┐
   └─────┬────────────┬─────────┘            │   MinIO      │
         │            │                      │ (artifacts)  │
         ▼            ▼                      └──────────────┘
   ┌──────────┐ ┌──────────┐
   │ Nuclei   │ │ OWASP    │── traffic ──> [Tenant Egress GW]
   │ Worker   │ │ ZAP      │              (NetworkPolicy +
   │ (Pod)    │ │ Worker   │               source-IP per tenant)
   └──────────┘ └──────────┘                      │
                                                  ▼
                                          [Target Website]
```

---

## Components

### 1. Frontend — `cobweb-web` (Next.js 15 + TS)

- **UX inspiration:** Rapid7 InsightAppSec / Acunetix — left nav (Dashboard / Projects / Scans / Vulnerabilities / Targets / Reports / Integrations / Audit / Admin), top bar with org switcher + user menu
- **Key screens:**
  - **Dashboard:** scan trend, vuln by severity (Critical/High/Med/Low/Info), top vulnerable targets, MTTR widget
  - **Scan Wizard:** Target → Profile (Quick / Full / Custom Nuclei templates / ZAP policy) → Auth (form login / cookie / header) → Scope (in/out URL regex) → Schedule → Notification
  - **Scan Detail:** real-time progress (WebSocket), request/response viewer, timeline, finding tree
  - **Diff View:** เปรียบเทียบ scan 2 ครั้ง — new findings / fixed / regression / unchanged
  - **Vulnerability Mgmt:** kanban (New → Triaged → In Progress → Resolved → Verified / FalsePositive / Accepted), bulk actions, SLA timer
  - **Reports:** template gallery (Executive / Technical / PCI-DSS / OWASP Top 10 / ISO 27001) + PDF/HTML/JSON export
- **State/Data:** TanStack Query + Zustand, JWT in httpOnly cookie + CSRF token
- **Realtime:** WebSocket subscription per scan (`/ws/scans/{id}`) for live progress

### 2. API Gateway / Public API — FastAPI

- ใช้ **FastAPI** ตัวเดียว serve ทั้ง internal และ public โดยแยก router
  - `/api/v1/...` → internal (cookie auth, สำหรับ frontend)
  - `/public/v1/...` → public (API key auth, สำหรับ CI/CD + 3rd-party)
- **Middleware stack:** request-id, structured logging (loguru), rate limit (slowapi + Redis), tenant resolution, RBAC enforcement, audit log emitter
- **OpenAPI 3.1** spec auto-generated → publish ที่ `/docs` + `/openapi.json` สำหรับ 3rd-party

### 3. Core Services (modular monolith ใน FastAPI, แยกเป็น microservice ภายหลังได้)

| Service | หน้าที่ | จุดสำคัญ |
|---|---|---|
| **Auth & IdP** | login, MFA (TOTP/WebAuthn), SAML2/OIDC SSO, API key, RBAC | ใช้ `python-jose` + `authlib` + `pyotp`; sessions ใน Redis |
| **Project & Asset** | organization → project → target hierarchy, scope rules | soft-delete + version target config |
| **Scan Orchestrator** | สร้าง ScanJob, push เข้า queue, track state machine | state: `queued → running → completed/failed/cancelled` |
| **Scanner Adapter** | wrapper เรียก Nuclei/ZAP, parse output → unified finding model | ดู §4 |
| **Vulnerability Mgmt** | dedupe finding, lifecycle, SLA, false-positive | dedupe key = hash(target+template_id+location+param) |
| **Report** | PDF (WeasyPrint), HTML, JSON, compliance mapping | template ใช้ Jinja2 |
| **Notification** | dispatch ตาม channel preference + severity threshold | adapter pattern: SlackAdapter, TeamsAdapter, EmailAdapter, WebhookAdapter |
| **Template Updater** | sync nuclei-templates จาก GitHub, versioned cache | cron + git pull + signature verify |
| **Audit Log** | append-only event log | sink → OpenSearch + optional SIEM forwarder |
| **Integration Hub** | Jira / GitHub / GitLab issue sync, SIEM forwarder | bidirectional state sync |

### 4. Scanner Workers (containerized, Kubernetes Job)

- **Nuclei Worker:**
  - Image: `projectdiscovery/nuclei:latest` + thin Python sidecar (`scanner-runner`)
  - รับ job ผ่าน RabbitMQ, mount template volume (read-only PVC จาก Template Updater), execute, stream finding กลับเป็น JSONL → MinIO + DB
- **ZAP Worker:**
  - Image: `zaproxy/zap-stable` headless mode + `python-owasp-zap-v2.4` sidecar
  - Spider → AJAX Spider → Active Scan → export JSON/XML → MinIO
  - รองรับ context file (auth, scope, technology hints)
- **Common pattern:**
  - แต่ละ scan = K8s Job (TTL 1h after completion) — ephemeral, no shared state
  - Resource request/limit: cpu=1-2 / mem=2-4Gi / scan
  - Pod Security: non-root, readOnlyRootFilesystem, drop ALL capabilities
  - **Network egress:** Pod แนบ Annotation `tenant-id=...` → CNI (Cilium/Calico) NetworkPolicy route ออก gateway dedicated IP per tenant (Recommended approach: ใช้ **egress gateway pattern** ของ Cilium หรือ NAT gateway pool)
  - Supply-chain: image signed (cosign), pinned by digest, SBOM generated

### 5. Data Layer

| Store | ใช้สำหรับ | Schema highlights |
|---|---|---|
| **PostgreSQL 16** (primary) | users, orgs, projects, targets, scans metadata, vulns, audit | row-level security (RLS) per tenant_id |
| **TimescaleDB extension** | scan metrics time-series (duration, finding counts trend) | hypertable on `scan_metrics` |
| **Redis 7** | session, rate limit, job lock, cache, websocket pubsub | TTL-based |
| **RabbitMQ** | scan job queue, event bus | quorum queues, dead-letter |
| **OpenSearch** | audit log, full-text search on findings, SIEM-ready | ILM 90d hot → 1y warm |
| **MinIO** | scan artifacts (HAR, screenshot, raw nuclei jsonl, ZAP report.xml, generated PDF reports) | bucket per tenant, server-side encryption |

---

## Data Model (key entities)

```
Organization (1) ─< Project (1) ─< Target (1) ─< Scan (1) ─< Finding
                       │                            │
                       └─< ScanProfile              └─< ScanArtifact (→ MinIO key)
User ─< OrgMember (role) ─< Project membership
ApiToken (org scoped) — for CI/CD
Vulnerability (logical) ─< Finding (per-scan instance)
                        ─< IntegrationRef (Jira issue id, GH issue id)
AuditLog (append-only)
NotificationRule (project + channel + severity threshold)
TemplateVersion (nuclei pack, ZAP policy pack) — versioned, immutable
```

**RBAC roles:**
- **Admin (org-level):** ทุกอย่าง รวม billing, SSO config, audit export
- **Project Admin:** จัดการ project + target + member ของ project นั้น
- **User:** สร้าง scan, ดู finding, จัดการ vuln state ของ project ที่อยู่
- **Auditor:** read-only ทุก project + audit log access (ห้าม trigger scan)

ใช้ **Casbin** (Python) สำหรับ policy enforcement; permission model = `(role, resource, action, scope)`

---

## Critical Workflows

### A) Scan Creation & Execution
```
User → POST /scans { target, profile, schedule? }
  → Orchestrator: validate scope, RBAC, target ownership
  → INSERT scan(status=queued)
  → publish scan.created → RabbitMQ
  → Worker (K8s Job spawned by controller) consumes
  → status=running, emit websocket events
  → finding stream → DB + MinIO
  → status=completed → trigger: Notification, IntegrationHub, Diff
```

### B) Vulnerability Lifecycle (state machine)
```
NEW ─(triage)→ TRIAGED ─(assign)→ IN_PROGRESS ─(fix+rescan)→ RESOLVED ─(verify scan)→ VERIFIED
  └─(mark)→ FALSE_POSITIVE
  └─(mark)→ ACCEPTED_RISK (with expiry date)
RESOLVED ─(found again next scan)→ REGRESSION (special state, alerts)
```
SLA timer ตาม severity (เช่น Critical=7d, High=14d, Medium=30d) — config ระดับ org

### C) CI/CD Integration
```
CI runner → POST /public/v1/scans (X-Api-Key)
   { target_url, profile=quick, wait=true, threshold=critical }
→ orchestrator runs scan synchronously up to wait_timeout
→ return { status, summary, fail_build: bool, report_url }
→ CI ใช้ exit code ตัดสิน pass/fail
```
**CLI tool:** `cobweb-cli scan --url ... --threshold critical --wait` (Go binary หรือ Python wheel) — distribute ผ่าน GitHub Releases + Docker image

### D) Diff / Comparison
- เก็บ `dedupe_hash` ของทุก finding
- เมื่อ scan ใหม่เสร็จ → query findings ของ scan ล่าสุด vs scan ก่อนหน้าของ target เดียวกัน
- Categorize: `NEW` / `FIXED` / `RECURRING` / `REGRESSION (was RESOLVED, now back)`
- แสดง Diff View บน UI + ส่ง notification

### E) Template / Signature Update
- **Nuclei:** cron daily — `git pull projectdiscovery/nuclei-templates` → verify signature → tag version → push to PVC ที่ workers mount
- **ZAP:** `zap-cli update` ใน base image build pipeline (rebuild image รายสัปดาห์)
- Maintain `TemplateVersion` record — แต่ละ scan ผูกกับ version ที่ใช้ → reproducible
- Admin UI ดู changelog + manual trigger update

### F) Audit Log
- Middleware emit event ทุก mutating request: `{actor, tenant, resource, action, ip, ua, before, after, ts}`
- Sink → OpenSearch (90 วัน hot) + optional async forward → SIEM
- Immutable: append-only, hash-chained (each entry includes hash of prev)
- Export CSV/JSON สำหรับ Auditor role

---

## Security Considerations

1. **Multi-tenant isolation:** PostgreSQL RLS + tenant_id ใน JWT claim + Redis key namespace + MinIO bucket-per-tenant + scanner egress IP per tenant
2. **Scan abuse prevention:**
   - Target ownership verification (DNS TXT record / file upload / meta tag) ก่อน scan ครั้งแรก
   - Rate limit scans per org/per target
   - Scope enforcement — ห้าม scan IP private ranges, cloud metadata endpoints (169.254.169.254), localhost
3. **Secret management:** HashiCorp Vault หรือ K8s Secrets + Sealed-Secrets; เก็บ target login creds เข้ารหัสด้วย envelope encryption
4. **Supply chain:** signed images (cosign), SBOM (syft), vuln scan ของ image (trivy in CI)
5. **Network:** mTLS ระหว่าง services (Linkerd/Istio), NetworkPolicy default-deny
6. **Input validation:** Pydantic v2 strict models ทุก endpoint
7. **OWASP ASVS L2 compliance** สำหรับ platform เอง (กิน dogfood)

---

## Deployment / Infrastructure

- **Container:** ทุก service มี Dockerfile (multi-stage, distroless base), tagged by git SHA
- **K8s:** Helm chart `cobweb` ครอบทุก component; overlay per env (dev/stg/prod)
- **GitOps:** ArgoCD sync จาก infra repo
- **Autoscaling:**
  - API: HPA on CPU+RPS
  - Scanner workers: KEDA scale-from-zero ตาม RabbitMQ queue depth
- **Observability:**
  - Metrics: Prometheus + Grafana (dashboards: scan throughput, queue depth, p95 API latency, vuln trend)
  - Logs: Loki หรือ OpenSearch (structured JSON)
  - Tracing: OpenTelemetry → Jaeger
  - Alerts: AlertManager → PagerDuty/Slack
- **Backup:**
  - Postgres: pgBackRest, daily full + WAL, 30d retention, cross-region
  - MinIO: bucket replication
  - OpenSearch: snapshot to MinIO

---

## Repository Layout (proposed monorepo)

```
cobweb/
├── apps/
│   ├── web/                  # Next.js frontend
│   ├── api/                  # FastAPI core (modular monolith)
│   └── cli/                  # cobweb-cli for CI/CD
├── workers/
│   ├── nuclei-runner/        # sidecar wrapper
│   └── zap-runner/
├── packages/
│   ├── shared-schemas/       # Pydantic + TS types (generated)
│   └── ui-kit/               # shadcn-based components
├── deploy/
│   ├── helm/cobweb/          # Helm chart
│   ├── docker/               # Dockerfiles
│   └── argocd/               # GitOps manifests
├── docs/
│   ├── architecture/         # this file + ADRs
│   ├── api/                  # OpenAPI samples
│   └── runbooks/
└── tests/
    ├── e2e/                  # Playwright
    └── load/                 # k6
```

---

## Phased Implementation Roadmap

### Phase 0 — Foundations (2-3 wk)
- Bootstrap monorepo, CI (GitHub Actions), Helm skeleton, Postgres+Redis+RabbitMQ+MinIO local via docker-compose
- Auth service (local + MFA), Org/Project/User models, RBAC with Casbin

### Phase 1 — Core Scan (3-4 wk)
- Target management + ownership verification
- Scan Orchestrator + Nuclei worker (single profile)
- Finding ingestion + basic UI (list, detail)
- Realtime progress via WebSocket

### Phase 2 — ZAP + Vuln Mgmt (3-4 wk)
- ZAP worker integration
- Vulnerability lifecycle + dedupe + Diff view
- Audit log pipeline

### Phase 3 — Integrations (3-4 wk)
- Public API + API key + CI/CD CLI
- Notification (Slack/Teams/Email/Webhook)
- Bug tracker sync (Jira first, then GitHub/GitLab)

### Phase 4 — SSO + Compliance + Reports (2-3 wk)
- SAML2/OIDC SSO
- Compliance mapping (PCI-DSS, OWASP Top 10, ISO 27001) + report templates
- SIEM forwarder

### Phase 5 — Hardening + GA (2-3 wk)
- Tenant egress gateway, NetworkPolicies, RLS verification
- Load test (k6), chaos test
- Penetration test ของ platform เอง
- Docs + onboarding flow

---

## Critical Files to Create (when implementation begins)

| Path | Purpose |
|---|---|
| `apps/api/cobweb/main.py` | FastAPI app factory |
| `apps/api/cobweb/core/security.py` | JWT, password hashing, RBAC |
| `apps/api/cobweb/services/scan_orchestrator.py` | scan state machine + queue dispatch |
| `apps/api/cobweb/services/scanner_adapter/{nuclei,zap}.py` | adapter to unified finding model |
| `apps/api/cobweb/models/{org,project,target,scan,finding,vuln,audit}.py` | SQLAlchemy 2.0 models |
| `apps/api/cobweb/api/v1/router.py` + `apps/api/cobweb/api/public/router.py` | route registration |
| `workers/nuclei-runner/runner.py` + `workers/zap-runner/runner.py` | container entrypoint |
| `apps/web/app/(dashboard)/{scans,vulnerabilities,targets,reports}/page.tsx` | core UI screens |
| `deploy/helm/cobweb/values.yaml` | Helm chart values |

---

## Verification Plan

1. **Unit tests:** pytest (apps/api) ≥ 80% coverage on services + RBAC; vitest (apps/web)
2. **Integration tests:** spin up docker-compose stack, hit FastAPI endpoints with httpx, verify Postgres/Redis/Rabbit interaction
3. **E2E tests:** Playwright — login → create project → create target → run scan against bundled OWASP Juice Shop → see findings → mark FP → diff next scan
4. **Scanner correctness:** golden-file test — known-vulnerable target (DVWA, Juice Shop) ต้องเจอ vuln ที่คาดไว้
5. **CI/CD integration test:** `cobweb-cli scan --url <juice-shop> --threshold high --wait` ใน GitHub Action job → assert exit code = 1
6. **RBAC matrix test:** ทุกคู่ (role × endpoint × scope) — auto-generated from policy
7. **Multi-tenancy isolation test:** สร้าง 2 tenants, attempt cross-tenant access ผ่านทุก API → expect 404/403
8. **Load test (k6):** 100 concurrent scans, p95 API latency < 500ms, queue depth recovery < 5min
9. **Compliance check:** map findings → PCI-DSS Req 6.5 / OWASP Top 10 categories → verify report contains expected sections

---

## Open Questions / Future Considerations

- **Pricing/quota model** ของ SaaS (scans/mo, retention, concurrency tier) — design `Quota` table early
- **Authenticated scans:** form-login recorder UI (selenium-based) — Phase 6
- **AI assist:** LLM-based finding triage / fix suggestion — Phase 7+
- **Mobile app scanning** (MAST) — out of scope for v1, แต่ data model ควรรองรับ `target.type IN (web, api, mobile)`
- **API spec import:** OpenAPI/Postman → auto-generate ZAP context — high-value Phase 3 add-on
