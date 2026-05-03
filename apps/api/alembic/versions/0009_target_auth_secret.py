"""target.auth_secret_ciphertext

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "targets",
        sa.Column("auth_secret_ciphertext", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("targets", "auth_secret_ciphertext")
