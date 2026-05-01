from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from cobweb.db.base import Base, TimestampMixin


class AuditLog(Base, TimestampMixin):
    """Append-only audit log. Hash-chained — entry.hash = sha256(prev_hash + payload)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    org_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
