"""A scrap purchase: one lot, its GST mode and inbound transport."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import GstMode, PurchaseTransportMode, db_enum

if TYPE_CHECKING:
    from app.models.heat import HeatInput


class PurchaseLot(Base):
    __tablename__ = "purchase_lots"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    supplier: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    rate_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gst_mode: Mapped[GstMode] = mapped_column(
        db_enum(GstMode, "gst_mode"), nullable=False
    )
    transport_mode: Mapped[PurchaseTransportMode] = mapped_column(
        db_enum(PurchaseTransportMode, "purchase_transport_mode"), nullable=False
    )
    transport_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )

    inputs: Mapped[list[HeatInput]] = relationship(
        back_populates="lot", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("weight_kg > 0", name="weight_positive"),
        CheckConstraint("rate_per_kg > 0", name="rate_positive"),
        CheckConstraint("transport_cost >= 0", name="transport_non_negative"),
    )
