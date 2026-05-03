"""Best-effort compliance mappings.

These are starter mappings — for production, a security analyst should
maintain a vetted ruleset per regulation.

OWASP Top 10 (2021) categories
PCI-DSS Requirement 6.5
ISO 27001 Annex A controls (subset)

Lookup precedence:
  1. LLM-generated full template_id matches (compliance_map_llm.py — populated
     by `make bulk-map`). Tries the full id first, then the head segment.
  2. Curated prefix match against the static dicts below (head segment only).
  3. Curated substring match (handles e.g. nuclei templates that embed a known
     prefix mid-path).
"""

from __future__ import annotations

try:
    from cobweb.services.report_templates.compliance_map_llm import (
        LLM_TEMPLATE_TO_ISO,
        LLM_TEMPLATE_TO_OWASP,
        LLM_TEMPLATE_TO_PCI,
    )
except ImportError:  # the generated file is optional — empty fallback keeps imports safe
    LLM_TEMPLATE_TO_OWASP = {}
    LLM_TEMPLATE_TO_PCI = {}
    LLM_TEMPLATE_TO_ISO = {}

OWASP_TOP_10 = {
    "A01:2021": "Broken Access Control",
    "A02:2021": "Cryptographic Failures",
    "A03:2021": "Injection",
    "A04:2021": "Insecure Design",
    "A05:2021": "Security Misconfiguration",
    "A06:2021": "Vulnerable and Outdated Components",
    "A07:2021": "Identification and Authentication Failures",
    "A08:2021": "Software and Data Integrity Failures",
    "A09:2021": "Security Logging and Monitoring Failures",
    "A10:2021": "Server-Side Request Forgery",
}

# Heuristic by Nuclei tag/template-id prefix → OWASP category.
TEMPLATE_TO_OWASP: dict[str, str] = {
    "sqli": "A03:2021",
    "xss": "A03:2021",
    "rce": "A03:2021",
    "ssrf": "A10:2021",
    "lfi": "A01:2021",
    "auth": "A07:2021",
    "default-login": "A07:2021",
    "exposed-panels": "A05:2021",
    "exposures": "A05:2021",
    "tech": "A06:2021",
    "cves": "A06:2021",
    "misconfiguration": "A05:2021",
    "tls": "A02:2021",
    "ssl": "A02:2021",
}


def owasp_category(template_id: str) -> tuple[str, str] | None:
    """Returns (id, label) tuple, or None if no match."""
    if template_id in LLM_TEMPLATE_TO_OWASP:
        oid = LLM_TEMPLATE_TO_OWASP[template_id]
        if oid in OWASP_TOP_10:
            return oid, OWASP_TOP_10[oid]
    head = template_id.split("/", 1)[0].lower()
    if head in TEMPLATE_TO_OWASP:
        oid = TEMPLATE_TO_OWASP[head]
        return oid, OWASP_TOP_10[oid]
    for prefix, oid in TEMPLATE_TO_OWASP.items():
        if prefix in template_id.lower():
            return oid, OWASP_TOP_10[oid]
    return None


PCI_DSS_6_5 = {
    "6.5.1": "Injection flaws (SQLi, OS, LDAP)",
    "6.5.2": "Buffer overflows",
    "6.5.3": "Insecure cryptographic storage",
    "6.5.4": "Insecure communications",
    "6.5.5": "Improper error handling",
    "6.5.7": "Cross-site scripting (XSS)",
    "6.5.8": "Improper access control",
    "6.5.9": "Cross-site request forgery (CSRF)",
    "6.5.10": "Broken authentication and session management",
}

TEMPLATE_TO_PCI: dict[str, list[str]] = {
    "sqli": ["6.5.1"],
    "xss": ["6.5.7"],
    "csrf": ["6.5.9"],
    "auth": ["6.5.10"],
    "default-login": ["6.5.10"],
    "tls": ["6.5.4"],
    "ssl": ["6.5.4"],
    "lfi": ["6.5.8"],
    "exposed-panels": ["6.5.8"],
}


def pci_dss(template_id: str) -> list[tuple[str, str]]:
    if template_id in LLM_TEMPLATE_TO_PCI:
        items = LLM_TEMPLATE_TO_PCI[template_id]
    else:
        head = template_id.split("/", 1)[0].lower()
        items = TEMPLATE_TO_PCI.get(head, [])
    return [(req, PCI_DSS_6_5[req]) for req in items if req in PCI_DSS_6_5]


ISO_27001_CONTROLS = {
    "A.5.18": "Access rights",
    "A.8.2": "Privileged access rights",
    "A.8.3": "Information access restriction",
    "A.8.20": "Networks security",
    "A.8.21": "Security of network services",
    "A.8.24": "Use of cryptography",
    "A.8.28": "Secure coding",
}

TEMPLATE_TO_ISO: dict[str, list[str]] = {
    "auth": ["A.5.18", "A.8.2"],
    "default-login": ["A.8.3"],
    "exposed-panels": ["A.8.3"],
    "tls": ["A.8.24"],
    "ssl": ["A.8.24"],
    "sqli": ["A.8.28"],
    "xss": ["A.8.28"],
}


def iso_27001(template_id: str) -> list[tuple[str, str]]:
    if template_id in LLM_TEMPLATE_TO_ISO:
        items = LLM_TEMPLATE_TO_ISO[template_id]
    else:
        head = template_id.split("/", 1)[0].lower()
        items = TEMPLATE_TO_ISO.get(head, [])
    return [(c, ISO_27001_CONTROLS[c]) for c in items if c in ISO_27001_CONTROLS]
