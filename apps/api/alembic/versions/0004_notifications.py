"""notification_rules table

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    channel = sa.Enum(
        "slack", "teams", "email", "webhook", name="notification_channel"
    )
    op.create_table(
        "notification_rules",
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
            nullable=True,
            index=True,
        ),
        sa.Column("channel", channel, nullable=False),
        sa.Column("target", sa.String(2048), nullable=False),
        sa.Column("severity_threshold", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("config", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_rules")
    op.execute("DROP TYPE IF EXISTS notification_channel")
