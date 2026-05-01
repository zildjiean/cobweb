from __future__ import annotations

import enum

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from cobweb.db.base import Base, TimestampMixin, enum_col, new_uuid


class NotificationChannel(str, enum.Enum):
    SLACK = "slack"
    TEAMS = "teams"
    EMAIL = "email"
    WEBHOOK = "webhook"


class NotificationRule(Base, TimestampMixin):
    """Per-project rule: deliver scan-completion summary to a channel."""

    __tablename__ = "notification_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        enum_col(NotificationChannel, name="notification_channel"), nullable=False
    )
    target: Mapped[str] = mapped_column(String(2048), nullable=False)
    """For slack/webhook: URL. For email: comma-separated addresses."""
    severity_threshold: Mapped[str] = mapped_column(String(16), default="medium")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
