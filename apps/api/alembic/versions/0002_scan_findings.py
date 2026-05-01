"""scan + finding tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    scan_status = sa.Enum(
        "queued", "running", "completed", "failed", "cancelled", name="scan_status"
    )
    scan_profile = sa.Enum("quick", "full", "custom", name="scan_profile")
    severity = sa.Enum(
        "critical", "high", "medium", "low", "info", name="finding_severity"
    )

    op.create_table(
        "scans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "target_id",
            sa.String(36),
            sa.ForeignKey("targets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "triggered_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("profile", scan_profile, nullable=False, server_default="quick"),
        sa.Column("engine", sa.String(32), nullable=False, server_default="nuclei"),
        sa.Column("template_version", sa.String(64), nullable=True),
        sa.Column("status", scan_status, nullable=False, server_default="queued", index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("config", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("summary", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "scan_id",
            sa.String(36),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "target_id",
            sa.String(36),
            sa.ForeignKey("targets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("template_id", sa.String(255), nullable=False, index=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("severity", severity, nullable=False, index=True),
        sa.Column("matched_at", sa.String(2048), nullable=False),
        sa.Column("matcher_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("remediation", sa.Text, nullable=True),
        sa.Column("cve", sa.String(64), nullable=True, index=True),
        sa.Column("cwe", sa.String(64), nullable=True),
        sa.Column("cvss", sa.String(16), nullable=True),
        sa.Column("request", sa.Text, nullable=True),
        sa.Column("response", sa.Text, nullable=True),
        sa.Column("raw", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("dedupe_hash", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "scan_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "scan_id",
            sa.String(36),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scan_artifacts")
    op.drop_table("findings")
    op.drop_table("scans")
    op.execute("DROP TYPE IF EXISTS finding_severity")
    op.execute("DROP TYPE IF EXISTS scan_profile")
    op.execute("DROP TYPE IF EXISTS scan_status")
