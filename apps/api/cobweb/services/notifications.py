"""Notification dispatcher — adapter pattern.

Channels: Slack (incoming webhook), Teams (incoming webhook), Generic Webhook,
Email (SMTP, optional). Email config is global (smtp_host/user/pass via env);
target field is the recipient list.

Severity threshold: only fire if scan summary contains a finding ≥ threshold.
"""

from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
from typing import Any, Protocol

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.settings import get_settings
from cobweb.models.notification import NotificationChannel, NotificationRule
from cobweb.models.scan import Scan

THRESHOLD_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _meets_threshold(summary: dict[str, int], threshold: str) -> bool:
    cutoff = THRESHOLD_RANK.get(threshold, 2)
    return any(
        n and THRESHOLD_RANK.get(sev, -1) >= cutoff for sev, n in summary.items()
    )


class Adapter(Protocol):
    async def send(self, rule: NotificationRule, payload: dict[str, Any]) -> None: ...


class SlackAdapter:
    """Posts to a Slack incoming webhook URL."""

    async def send(self, rule: NotificationRule, payload: dict[str, Any]) -> None:
        text = (
            f"*Cobweb scan completed* — {payload['target_url']}\n"
            f"Status: `{payload['status']}` | Findings: {payload['summary']}"
        )
        body = {
            "text": text,
            "attachments": [
                {
                    "color": "danger" if _meets_threshold(payload["summary"], "high") else "warning",
                    "fields": [
                        {"title": k, "value": str(v), "short": True}
                        for k, v in payload["summary"].items()
                    ],
                }
            ],
        }
        async with httpx.AsyncClient(timeout=10.0) as c:
            await c.post(rule.target, json=body)


class TeamsAdapter:
    """Microsoft Teams incoming webhook (MessageCard format)."""

    async def send(self, rule: NotificationRule, payload: dict[str, Any]) -> None:
        body = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": "Cobweb scan completed",
            "themeColor": "E5484D"
            if _meets_threshold(payload["summary"], "high")
            else "F5A623",
            "title": f"Scan completed — {payload['target_url']}",
            "sections": [
                {
                    "facts": [
                        {"name": k, "value": str(v)}
                        for k, v in payload["summary"].items()
                    ]
                }
            ],
        }
        async with httpx.AsyncClient(timeout=10.0) as c:
            await c.post(rule.target, json=body)


class WebhookAdapter:
    """Generic JSON webhook — POSTs the full payload as-is."""

    async def send(self, rule: NotificationRule, payload: dict[str, Any]) -> None:
        async with httpx.AsyncClient(timeout=10.0) as c:
            await c.post(rule.target, json=payload, headers={"User-Agent": "Cobweb/1.0"})


class EmailAdapter:
    """Plain SMTP — synchronous (called via run_in_executor in dispatch)."""

    async def send(self, rule: NotificationRule, payload: dict[str, Any]) -> None:
        s = get_settings()
        host = getattr(s, "smtp_host", "") or rule.config.get("smtp_host")
        if not host:
            logger.warning("Email skipped: no SMTP host configured")
            return
        msg = EmailMessage()
        msg["Subject"] = f"Cobweb: scan {payload['scan_id'][:8]} — {payload['status']}"
        msg["From"] = rule.config.get("from", "noreply@cobweb.local")
        msg["To"] = rule.target
        msg.set_content(json.dumps(payload, indent=2))
        # Synchronous send — email volume is low so we don't bother with aiosmtp here
        port = int(rule.config.get("port", 587))
        with smtplib.SMTP(host, port) as srv:
            user = rule.config.get("user")
            password = rule.config.get("password")
            if user and password:
                srv.starttls()
                srv.login(user, password)
            srv.send_message(msg)


ADAPTERS: dict[NotificationChannel, Adapter] = {
    NotificationChannel.SLACK: SlackAdapter(),
    NotificationChannel.TEAMS: TeamsAdapter(),
    NotificationChannel.WEBHOOK: WebhookAdapter(),
    NotificationChannel.EMAIL: EmailAdapter(),
}


async def dispatch_scan_completed(
    db: AsyncSession, scan: Scan, target_url: str
) -> int:
    """Look up enabled rules matching this scan's project (or org-wide null project),
    filter by severity threshold, send via adapter. Returns count of deliveries."""
    summary = {k: int(v) for k, v in (scan.summary or {}).items()}
    payload = {
        "scan_id": scan.id,
        "project_id": scan.project_id,
        "target_id": scan.target_id,
        "target_url": target_url,
        "status": scan.status.value if hasattr(scan.status, "value") else str(scan.status),
        "summary": summary,
        "engine": scan.engine,
        "profile": scan.profile.value if hasattr(scan.profile, "value") else str(scan.profile),
    }

    res = await db.execute(
        select(NotificationRule).where(
            NotificationRule.org_id == scan.org_id,
            NotificationRule.enabled.is_(True),
        )
    )
    sent = 0
    for rule in res.scalars().all():
        if rule.project_id and rule.project_id != scan.project_id:
            continue
        if not _meets_threshold(summary, rule.severity_threshold):
            continue
        adapter = ADAPTERS.get(rule.channel)
        if not adapter:
            continue
        try:
            await adapter.send(rule, payload)
            sent += 1
        except Exception:  # noqa: BLE001
            logger.exception("notification dispatch failed for rule={}", rule.id)
    return sent
