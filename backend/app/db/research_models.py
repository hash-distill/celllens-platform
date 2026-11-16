"""Additive research annotations; scientific artifacts remain immutable."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.models import Base


class ResearchFindingModel(Base):
    __tablename__ = "research_findings"
    __table_args__ = (Index("ix_findings_record_created", "record_kind", "record_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    record_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    record_id: Mapped[str] = mapped_column(String(80), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    selection_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
