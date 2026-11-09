"""Workshop settings: one row, id = 1."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    gst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.18")
    )
    planned_yield_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("89.00")
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("gst_rate >= 0 AND gst_rate < 1", name="gst_rate_range"),
        CheckConstraint(
            "planned_yield_pct > 0 AND planned_yield_pct <= 100",
            name="yield_pct_range",
        ),
    )
