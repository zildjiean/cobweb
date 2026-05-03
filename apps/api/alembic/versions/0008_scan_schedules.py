"""scan_schedules

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schedule_freq = postgresql.ENUM(
        "hourly", "daily", "weekly", "monthly", name="schedule_frequency"
    )
    schedule_freq.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "scan_schedules",
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
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "profile",
            postgresql.ENUM(name="scan_profile", create_type=False),
            nullable=False,
            server_default="quick",
        ),
        sa.Column("engine", sa.String(32), nullable=False, server_default="nuclei"),
        sa.Column(
            "frequency",
            postgresql.ENUM(name="schedule_frequency", create_type=False),
            nullable=False,
        ),
        sa.Column("hour_of_day", sa.Integer, nullable=False, server_default="0"),
        sa.Column("day_of_week", sa.Integer, nullable=False, server_default="0"),
        sa.Column("day_of_month", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "enabled", sa.Boolean, nullable=False, server_default=sa.text("true"), index=True
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scan_id", sa.String(36), nullable=True),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_table("scan_schedules")
    op.execute("DROP TYPE IF EXISTS schedule_frequency")
