"""cobweb-cli — wrap the Cobweb public API for CI/CD pipelines.

Usage:
    cobweb-cli scan --url https://app.example.com --threshold high --wait
    cobweb-cli scan --url https://app.example.com --no-wait

Env:
    COBWEB_API_BASE  (default https://cobweb.local)
    COBWEB_API_KEY   (required) — created in dashboard → Integrations
"""

from __future__ import annotations

import os
import sys

import click
import httpx
from rich.console import Console
from rich.table import Table

console = Console()


def _api_base() -> str:
    return os.getenv("COBWEB_API_BASE", "https://cobweb.local").rstrip("/")


def _api_key() -> str:
    key = os.getenv("COBWEB_API_KEY", "")
    if not key:
        console.print("[red]COBWEB_API_KEY not set[/red]")
        sys.exit(2)
    return key


@click.group()
def cli() -> None:
    """Cobweb DAST CLI."""


@cli.command()
@click.option("--url", required=True, help="Target URL to scan (must be a verified target)")
@click.option(
    "--profile",
    default="quick",
    type=click.Choice(["quick", "full", "custom"]),
    show_default=True,
)
@click.option(
    "--engine",
    default="nuclei",
    type=click.Choice(["nuclei", "zap"]),
    show_default=True,
)
@click.option(
    "--threshold",
    default="high",
    type=click.Choice(["critical", "high", "medium", "low"]),
    show_default=True,
    help="Fail build if any finding ≥ threshold",
)
@click.option("--wait/--no-wait", default=True, show_default=True)
@click.option("--timeout", default=600, show_default=True, help="Wait timeout (seconds)")
@click.option(
    "--insecure",
    is_flag=True,
    help="Skip TLS verification (only for local/dev API endpoints)",
)
def scan(
    url: str,
    profile: str,
    engine: str,
    threshold: str,
    wait: bool,
    timeout: int,
    insecure: bool,
) -> None:
    """Trigger a DAST scan and (by default) wait for results."""
    payload = {
        "target_url": url,
        "profile": profile,
        "engine": engine,
        "threshold": threshold,
        "wait": wait,
        "wait_timeout_s": timeout,
    }
    headers = {"X-Api-Key": _api_key(), "Content-Type": "application/json"}

    with httpx.Client(verify=not insecure, timeout=timeout + 30) as c:
        r = c.post(f"{_api_base()}/public/v1/scans", json=payload, headers=headers)
        if r.status_code >= 300:
            console.print(f"[red]API error {r.status_code}:[/red] {r.text}")
            sys.exit(2)
        body = r.json()

    console.print(f"[bold]Scan ID:[/bold] {body['scan_id']}")
    console.print(f"[bold]Status:[/bold]  {body['status']}")

    summary = body.get("findings") or {}
    table = Table(title="Findings by severity", show_header=True)
    table.add_column("Severity", style="bold")
    table.add_column("Count", justify="right")
    for sev in ("critical", "high", "medium", "low", "info"):
        n = summary.get(sev, 0)
        color = {
            "critical": "red",
            "high": "red",
            "medium": "yellow",
            "low": "green",
            "info": "dim",
        }[sev]
        table.add_row(f"[{color}]{sev}[/{color}]", str(n))
    console.print(table)

    if body.get("fail_build"):
        console.print(f"[red]✗ Build failed — finding ≥ {threshold}[/red]")
        sys.exit(1)
    console.print("[green]✓ Build passes[/green]")


@cli.command()
def version() -> None:
    """Show CLI version."""
    from cobweb_cli import __version__

    console.print(f"cobweb-cli {__version__}")


if __name__ == "__main__":
    cli()
