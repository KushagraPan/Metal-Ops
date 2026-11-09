"""A sale of alloy or byproduct, with its GST and outbound transport mode."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import GstMode, ItemType, SaleTransportMode, db_enum

if TYPE_CHECKING:
    from app.models.heat import Heat


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    customer: Mapped[str] = mapped_column(String(200), nullable=False)
    item_type: Mapped[ItemType] = mapped_column(
        db_enum(ItemType, "item_type"), nullable=False
    )
    heat_id: Mapped[int | None] = mapped_column(
        ForeignKey("heats.id", ondelete="RESTRICT"), index=True
    )
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    rate_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gst_mode: Mapped[GstMode] = mapped_column(
        db_enum(GstMode, "gst_mode"), nullable=False
    )
    transport_mode: Mapped[SaleTransportMode] = mapped_column(
        db_enum(SaleTransportMode, "sale_transport_mode"), nullable=False
    )
    transport_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    transport_billed: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )

    heat: Mapped[Heat | None] = relationship(back_populates="sales")

    __table_args__ = (
        CheckConstraint("weight_kg > 0", name="weight_positive"),
        CheckConstraint("rate_per_kg > 0", name="rate_positive"),
        CheckConstraint("transport_cost >= 0", name="transport_cost_non_negative"),
        CheckConstraint(
            "transport_billed >= 0", name="transport_billed_non_negative"
        ),
    )
