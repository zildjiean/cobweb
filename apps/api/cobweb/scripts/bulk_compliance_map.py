"""Bulk-classify finding templates into OWASP/PCI/ISO categories via LLM.

One-shot job: pulls distinct template_id values from the findings table,
sends them to the org's configured LLM provider in a single batch call, and
writes the result to `compliance_map_llm.py` (loaded at runtime by
`compliance_map.py` as a higher-precedence layer above the curated prefix
dicts).

Usage:
    cd apps/api && uv run python -m cobweb.scripts.bulk_compliance_map [options]

Options:
    --org-id <uuid>     Org whose LLM credentials to use. Auto-picked if
                        exactly one org has credentials configured.
    --dry-run           Print parsed mapping; don't write the output file.
    --include-mapped    Re-classify even templates already covered by the
                        static compliance_map.py (default: skip them).
    --limit N           Max templates per LLM call (default 50).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from cobweb.core.crypto import decrypt
from cobweb.db.base import get_sessionmaker
from cobweb.models.llm import OrgLLMSettings
from cobweb.models.scan import Finding
from cobweb.services.llm import LLMError, get_provider
from cobweb.services.report_templates import compliance_map

OUTPUT_FILE = (
    Path(__file__).resolve().parent.parent
    / "services"
    / "report_templates"
    / "compliance_map_llm.py"
)


def _build_system_prompt() -> str:
    owasp_list = "\n".join(
        f"- {oid}: {label}" for oid, label in compliance_map.OWASP_TOP_10.items()
    )
    pci_list = "\n".join(
        f"- {req}: {label}" for req, label in compliance_map.PCI_DSS_6_5.items()
    )
    iso_list = "\n".join(
        f"- {ctrl}: {label}" for ctrl, label in compliance_map.ISO_27001_CONTROLS.items()
    )
    return f"""You are a security-compliance mapping classifier. For each
web-application finding template_id, return its OWASP Top 10 (2021) category
and any matching PCI-DSS Requirement 6.5.x sub-requirements and ISO 27001:2022
Annex A controls.

Use ONLY the IDs from these reference tables:

OWASP Top 10 (2021):
{owasp_list}

PCI-DSS Requirement 6.5:
{pci_list}

ISO 27001 Annex A (subset):
{iso_list}

Rules:
- "owasp" must be a single OWASP id like "A03:2021", or null when no fit.
- "pci" must be a list (possibly empty) of strings like "6.5.7".
- "iso" must be a list (possibly empty) of strings like "A.8.24".
- Be conservative: if uncertain, prefer null / empty list.
- Template-id formats you'll see:
  - ZAP plugins: "zap/<plugin_id>" (e.g. zap/10038 = CSP header missing → A05)
  - Nuclei templates: slash-paths or hyphenated names (e.g. cookies-without-httponly,
    phpinfo-files, sqli/blind-time-based)

Return ONLY a single JSON object, no commentary, no markdown fence:
{{"results": [{{"template_id": "...", "owasp": "A05:2021", "pci": ["6.5.5"], "iso": ["A.5.18"]}}, ...]}}
"""


async def _gather_templates(db) -> list[str]:
    res = await db.execute(select(Finding.template_id).distinct())
    return sorted({row[0] for row in res.all() if row[0]})


def _already_mapped(tid: str) -> bool:
    return bool(
        compliance_map.owasp_category(tid)
        or compliance_map.pci_dss(tid)
        or compliance_map.iso_27001(tid)
    )


def _parse_response(text: str) -> list[dict]:
    """Strip optional markdown fence and parse the JSON payload."""
    s = text.strip()
    if s.startswith("```"):
        s = s[3:]
        if s.lower().startswith("json"):
            s = s[4:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    payload = json.loads(s)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("response missing 'results' list")
    return payload["results"]


def _filter_valid(rows: list[dict]) -> tuple[dict, dict, dict]:
    """Return (owasp_map, pci_map, iso_map), discarding any unknown ids."""
    owasp: dict[str, str] = {}
    pci: dict[str, list[str]] = {}
    iso: dict[str, list[str]] = {}
    for r in rows:
        tid = r.get("template_id")
        if not isinstance(tid, str) or not tid:
            continue
        ow = r.get("owasp")
        if isinstance(ow, str) and ow in compliance_map.OWASP_TOP_10:
            owasp[tid] = ow
        ps = [p for p in (r.get("pci") or []) if p in compliance_map.PCI_DSS_6_5]
        if ps:
            pci[tid] = ps
        ic = [c for c in (r.get("iso") or []) if c in compliance_map.ISO_27001_CONTROLS]
        if ic:
            iso[tid] = ic
    return owasp, pci, iso


def _load_existing() -> tuple[dict, dict, dict]:
    """Read the current compliance_map_llm.py dicts so incremental runs preserve them.

    Returns ({}, {}, {}) if the file is missing or fails to import — bootstrap-safe.
    """
    try:
        from cobweb.services.report_templates.compliance_map_llm import (
            LLM_TEMPLATE_TO_ISO,
            LLM_TEMPLATE_TO_OWASP,
            LLM_TEMPLATE_TO_PCI,
        )
        return dict(LLM_TEMPLATE_TO_OWASP), dict(LLM_TEMPLATE_TO_PCI), dict(LLM_TEMPLATE_TO_ISO)
    except ImportError:
        return {}, {}, {}


def _format_dict_literal(d: dict) -> str:
    """Render a dict as a deterministic Python literal (sorted keys, 4-space indent)."""
    if not d:
        return "{}"
    lines = ["{"]
    for k in sorted(d):
        v = d[k]
        if isinstance(v, list):
            inner = ", ".join(repr(x) for x in v)
            lines.append(f"    {k!r}: [{inner}],")
        else:
            lines.append(f"    {k!r}: {v!r},")
    lines.append("}")
    return "\n".join(lines)


def _write_output(owasp: dict, pci: dict, iso: dict) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = f'''"""LLM-generated full-template-id → compliance category mappings.

Generated by `python -m cobweb.scripts.bulk_compliance_map` at {ts}.
Edit the static curated dicts in `compliance_map.py` instead — those take
priority for templates a human has reviewed.

The lookup helpers in `compliance_map.py` consult these dicts first (exact
template_id match), then fall back to the curated prefix/substring matching.
"""

from __future__ import annotations

LLM_TEMPLATE_TO_OWASP: dict[str, str] = {_format_dict_literal(owasp)}

LLM_TEMPLATE_TO_PCI: dict[str, list[str]] = {_format_dict_literal(pci)}

LLM_TEMPLATE_TO_ISO: dict[str, list[str]] = {_format_dict_literal(iso)}
'''
    OUTPUT_FILE.write_text(body)


async def _resolve_settings(db, org_id: str | None) -> OrgLLMSettings:
    if org_id:
        s = await db.get(OrgLLMSettings, org_id)
        if not s:
            raise SystemExit(f"no LLM settings for org {org_id}")
        if not s.api_key_ciphertext:
            raise SystemExit(f"org {org_id} has no api_key_ciphertext")
        return s
    res = await db.execute(select(OrgLLMSettings))
    configured = [s for s in res.scalars() if s.api_key_ciphertext]
    if not configured:
        raise SystemExit("no org has LLM credentials configured — run with --org-id, or set credentials in the org settings UI")
    if len(configured) > 1:
        ids = ", ".join(s.org_id for s in configured)
        raise SystemExit(f"multiple orgs with credentials ({ids}); specify --org-id")
    return configured[0]


async def _amain(args: argparse.Namespace) -> int:
    Session = get_sessionmaker()
    async with Session() as db:
        settings = await _resolve_settings(db, args.org_id)
        api_key = decrypt(settings.api_key_ciphertext)
        all_tids = await _gather_templates(db)

    if args.include_mapped:
        todo = all_tids
    else:
        todo = [t for t in all_tids if not _already_mapped(t)]
    skipped = len(all_tids) - len(todo)
    print(
        f"org={settings.org_id} provider={settings.provider} model={settings.model}",
        file=sys.stderr,
    )
    print(
        f"templates total={len(all_tids)} todo={len(todo)} skipped(already mapped)={skipped}",
        file=sys.stderr,
    )
    if not todo:
        print("nothing to do", file=sys.stderr)
        return 0

    provider = get_provider(settings.provider)
    system_prompt = _build_system_prompt()
    all_results: list[dict] = []
    for i in range(0, len(todo), args.limit):
        batch = todo[i : i + args.limit]
        user = "Classify these template_ids:\n" + "\n".join(f"- {t}" for t in batch)
        print(
            f"  calling LLM (batch {i // args.limit + 1}, {len(batch)} templates)…",
            file=sys.stderr,
        )
        try:
            resp = await provider.generate(
                model=settings.model,
                system=system_prompt,
                user=user,
                api_key=api_key,
            )
        except LLMError as exc:
            print(f"LLM error: {exc}", file=sys.stderr)
            return 3
        try:
            rows = _parse_response(resp.content)
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"failed to parse JSON: {exc}", file=sys.stderr)
            print("raw response (first 1000 chars):", file=sys.stderr)
            print(resp.content[:1000], file=sys.stderr)
            return 4
        all_results.extend(rows)

    owasp_new, pci_new, iso_new = _filter_valid(all_results)
    print(
        f"classified: owasp={len(owasp_new)} pci={len(pci_new)} iso={len(iso_new)} "
        f"(of {len(todo)} requested)",
        file=sys.stderr,
    )

    if args.dry_run:
        print(json.dumps(
            {"owasp": owasp_new, "pci": pci_new, "iso": iso_new},
            indent=2, sort_keys=True,
        ))
        return 0

    # Merge new results onto existing dicts so incremental runs preserve prior
    # work. The default flow skips templates that are already mapped, so without
    # this merge we'd shrink the file from N entries to whatever's new (often 0
    # or a handful). New values win for the same template_id.
    owasp_existing, pci_existing, iso_existing = _load_existing()
    owasp_map = {**owasp_existing, **owasp_new}
    pci_map = {**pci_existing, **pci_new}
    iso_map = {**iso_existing, **iso_new}
    print(
        f"merged: owasp={len(owasp_map)} pci={len(pci_map)} iso={len(iso_map)} "
        f"(was: owasp={len(owasp_existing)} pci={len(pci_existing)} iso={len(iso_existing)})",
        file=sys.stderr,
    )

    _write_output(owasp_map, pci_map, iso_map)
    print(f"wrote {OUTPUT_FILE}", file=sys.stderr)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--org-id", help="Org UUID (auto-picked if exactly one is configured)")
    p.add_argument("--dry-run", action="store_true", help="Print mapping JSON; don't write file")
    p.add_argument(
        "--include-mapped",
        action="store_true",
        help="Re-classify templates already covered by the static map",
    )
    p.add_argument("--limit", type=int, default=50, help="Templates per LLM call (default 50)")
    args = p.parse_args()
    sys.exit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
