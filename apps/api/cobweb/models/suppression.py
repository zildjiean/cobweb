from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cobweb.db.base import Base, TimestampMixin, new_uuid


class FindingSuppression(Base, TimestampMixin):
    """Auto-suppress findings by (target, dedupe_hash) for a TTL.

    Created when a Vulnerability transitions to FALSE_POSITIVE; future Findings
    matching the same dedupe_hash on that target will land directly in
    FALSE_POSITIVE state until the suppression expires or is explicitly removed.
    """

    __tablename__ = "finding_suppressions"
    __table_args__ = (
        UniqueConstraint("target_id", "dedupe_hash", name="uq_suppression_target_dedupe"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("targets.id", ondelete="CASCADE"), index=True
    )
    dedupe_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
