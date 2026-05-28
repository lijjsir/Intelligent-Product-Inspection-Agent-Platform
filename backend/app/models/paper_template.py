from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TimestampMixin, UUIDBinary


class PaperTemplate(Base, TimestampMixin):
    __tablename__ = "paper_templates"

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    template_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    template_name: Mapped[str] = mapped_column(String(255), nullable=False)
    school_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    degree_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_bucket: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)


class PaperTemplateClause(Base, TimestampMixin):
    __tablename__ = "paper_template_clauses"
    __table_args__ = (UniqueConstraint("template_id", "clause_id", name="uq_paper_template_clause"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    template_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    clause_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_clause_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clause_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    applies_to: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rule_codes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(191), nullable=True)


class PaperTemplateRule(Base, TimestampMixin):
    __tablename__ = "paper_template_rules"
    __table_args__ = (UniqueConstraint("template_id", "rule_code", name="uq_paper_template_rule"),)

    id: Mapped[str] = mapped_column(UUIDBinary, primary_key=True, default=lambda: str(uuid7()))
    template_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    rule_code: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    check_type: Mapped[str] = mapped_column(String(64), nullable=False)
    expected: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_clause_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
