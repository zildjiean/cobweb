"""add 'high' to scan_profile enum

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE scan_profile ADD VALUE IF NOT EXISTS 'high'")


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE; rolling back this enum value
    # would require recreating the type and rewriting every column that uses it.
    # Treat as one-way.
    pass
