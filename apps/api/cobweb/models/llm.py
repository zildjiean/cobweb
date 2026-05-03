from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cobweb.db.base import Base, TimestampMixin, new_uuid


DEFAULT_PROMPT_TEMPLATE = (
    "You are translating a web-application security finding for a Thai cybersecurity team. "
    "Translate the supplied content into Thai. Keep proper nouns, CVE / CWE identifiers, URLs, "
    "HTTP methods, header names, parameter names, payloads, code snippets, and command-line "
    "examples in the original English form — do not translate them. Translate the surrounding "
    "explanation, severity description, impact, and remediation into clear Thai that a "
    "security engineer can act on. Preserve markdown structure. Return only the translated "
    "text, no preamble or commentary."
)


class OrgLLMSettings(Base, TimestampMixin):
    """Per-org LLM credentials + default prompt for issue translation."""

    __tablename__ = "org_llm_settings"

    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_template: Mapped[str] = mapped_column(
        Text, nullable=False, default=DEFAULT_PROMPT_TEMPLATE
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class FindingTranslation(Base, TimestampMixin):
    """Cached translation of a single finding — keyed by (finding, lang, prompt_hash)."""

    __tablename__ = "finding_translations"
    __table_args__ = (
        UniqueConstraint(
            "finding_id", "lang", "prompt_hash", name="uq_finding_translation_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    finding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("findings.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    lang: Mapped[str] = mapped_column(String(8), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
