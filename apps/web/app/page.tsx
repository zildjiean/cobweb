import Link from "next/link";
import { ShieldCheck, Zap, GitCompareArrows, FileBarChart2 } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const FEATURES = [
  {
    icon: Zap,
    title: "Two engines, one workflow",
    body: "Nuclei templates for fast CVE-style detection plus OWASP ZAP spider + active scan for deep coverage.",
  },
  {
    icon: GitCompareArrows,
    title: "Diff every scan",
    body: "Automatic regression detection — see new, fixed, recurring, and regressed findings between runs.",
  },
  {
    icon: ShieldCheck,
    title: "Vulnerability lifecycle",
    body: "Built-in kanban board with triage, SLA timers, false-positive marking, and accepted-risk handling.",
  },
  {
    icon: FileBarChart2,
    title: "Compliance ready",
    body: "Map findings to OWASP Top 10 / PCI-DSS / ISO 27001 — exportable reports in HTML and PDF.",
  },
];

export default function HomePage() {
  return (
    <main className="relative isolate min-h-screen overflow-hidden">
      <div
        aria-hidden
        className="absolute -top-40 left-1/2 h-[500px] w-[800px] -translate-x-1/2 rounded-full bg-accent/15 blur-3xl"
      />
      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-subtle text-sm font-bold text-white shadow-glow">
            C
          </div>
          <span className="text-lg font-semibold tracking-tight">
            Cob<span className="text-accent">web</span>
          </span>
        </div>
        <div className="flex items-center gap-3">
          <a
            href={`${API_BASE}/docs`}
            target="_blank"
            rel="noopener"
            className="text-sm text-slate-400 hover:text-white"
          >
            API docs
          </a>
          <Link href="/login" className="btn-secondary text-sm">
            Sign in
          </Link>
        </div>
      </header>

      <section className="relative z-10 mx-auto max-w-3xl px-6 py-16 text-center md:py-24">
        <span className="pill mb-5 border border-accent/30 bg-accent/10 text-accent">
          self-hosted DAST
        </span>
        <h1 className="text-4xl font-bold tracking-tight md:text-6xl">
          Continuous web security
          <br />
          <span className="bg-gradient-to-r from-accent to-purple-400 bg-clip-text text-transparent">
            in your own stack
          </span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-base text-slate-400 md:text-lg">
          Multi-tenant DAST scanning powered by Nuclei and OWASP ZAP. Run on your
          infrastructure, integrate with CI/CD, and manage vulnerabilities end-to-end.
        </p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <Link href="/login" className="btn-primary px-5 py-2.5 text-base">
            Sign in to console
          </Link>
          <a
            href={`${API_BASE}/docs`}
            target="_blank"
            rel="noopener"
            className="btn-secondary px-5 py-2.5 text-base"
          >
            Browse the API
          </a>
        </div>
      </section>

      <section className="relative z-10 mx-auto max-w-6xl px-6 pb-24">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="card card-hover">
              <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-accent/15 text-accent">
                <Icon className="h-4 w-4" />
              </div>
              <h3 className="text-sm font-semibold">{title}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="relative z-10 border-t border-border-subtle/60 py-6 text-center text-xs text-slate-500">
        © Cobweb — Multi-tenant DAST scanning platform.
      </footer>
    </main>
  );
}
