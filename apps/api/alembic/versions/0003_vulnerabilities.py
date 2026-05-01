"""vulnerabilities table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    state = sa.Enum(
        "new", "triaged", "in_progress", "resolved", "verified",
        "false_positive", "accepted_risk", "regression",
        name="vuln_state",
    )

    op.create_table(
        "vulnerabilities",
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
        sa.Column("dedupe_hash", sa.String(64), nullable=False, index=True),
        sa.Column("template_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, index=True),
        sa.Column("state", state, nullable=False, server_default="new", index=True),
        sa.Column(
            "first_seen_scan_id",
            sa.String(36),
            sa.ForeignKey("scans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "last_seen_scan_id",
            sa.String(36),
            sa.ForeignKey("scans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "assigned_to",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("accepted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("target_id", "dedupe_hash", name="uq_vuln_target_dedupe"),
    )


def downgrade() -> None:
    op.drop_table("vulnerabilities")
    op.execute("DROP TYPE IF EXISTS vuln_state")
