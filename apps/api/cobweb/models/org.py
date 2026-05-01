from __future__ import annotations

import enum

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cobweb.db.base import Base, TimestampMixin, enum_col, new_uuid


class OrgRole(str, enum.Enum):
    ADMIN = "admin"
    PROJECT_ADMIN = "project_admin"
    USER = "user"
    AUDITOR = "auditor"


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)


class OrgMember(Base, TimestampMixin):
    __tablename__ = "org_members"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[OrgRole] = mapped_column(
        enum_col(OrgRole, name="org_role"), nullable=False, default=OrgRole.USER
    )
