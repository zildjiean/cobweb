from __future__ import annotations

import enum

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cobweb.db.base import Base, TimestampMixin, enum_col, new_uuid


class TargetStatus(str, enum.Enum):
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    DISABLED = "disabled"


class Target(Base, TimestampMixin):
    __tablename__ = "targets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    scope_includes: Mapped[list[str]] = mapped_column(JSON, default=list)
    scope_excludes: Mapped[list[str]] = mapped_column(JSON, default=list)
    auth_config: Mapped[dict] = mapped_column(JSON, default=dict)  # legacy / unused
    auth_secret_ciphertext: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Fernet-encrypted JSON: {"type": "header"|"cookie", ...}
    status: Mapped[TargetStatus] = mapped_column(
        enum_col(TargetStatus, name="target_status"),
        nullable=False,
        default=TargetStatus.PENDING_VERIFICATION,
    )
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
