"""Spectro report metadata. The bytes live in storage, not in the database."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ReportResult, db_enum

if TYPE_CHECKING:
    from app.models.heat import Heat


class SpectroReport(Base):
    __tablename__ = "spectro_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    heat_id: Mapped[int] = mapped_column(
        ForeignKey("heats.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sample_no: Mapped[str] = mapped_column(String(50), nullable=False)
    file_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    grade_tested: Mapped[str | None] = mapped_column(String(50))
    result: Mapped[ReportResult] = mapped_column(
        db_enum(ReportResult, "report_result"),
        nullable=False,
        default=ReportResult.PENDING,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    elements: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    heat: Mapped[Heat] = relationship(back_populates="reports")

    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
    )
