"""A furnace batch and the kilograms it takes from each lot."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import Alloy, db_enum

if TYPE_CHECKING:
    from app.models.purchase import PurchaseLot
    from app.models.report import SpectroReport
    from app.models.sale import Sale


class Heat(Base):
    __tablename__ = "heats"

    id: Mapped[int] = mapped_column(primary_key=True)
    heat_no: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    heat_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    alloy: Mapped[Alloy] = mapped_column(db_enum(Alloy, "alloy"), nullable=False)

    output_kg: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    dross_kg: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    iron_scrap_kg: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )

    oil_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    power_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    labour_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    other_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )

    inputs: Mapped[list[HeatInput]] = relationship(
        back_populates="heat",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sales: Mapped[list[Sale]] = relationship(
        back_populates="heat", passive_deletes=True
    )
    reports: Mapped[list[SpectroReport]] = relationship(
        back_populates="heat",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("output_kg >= 0", name="output_non_negative"),
        CheckConstraint("dross_kg >= 0", name="dross_non_negative"),
        CheckConstraint("iron_scrap_kg >= 0", name="iron_scrap_non_negative"),
        CheckConstraint("oil_cost >= 0", name="oil_cost_non_negative"),
        CheckConstraint("power_cost >= 0", name="power_cost_non_negative"),
        CheckConstraint("labour_cost >= 0", name="labour_cost_non_negative"),
        CheckConstraint("other_cost >= 0", name="other_cost_non_negative"),
    )


class HeatInput(Base):
    """Kilograms taken from one lot by one heat. The pair is the identity."""

    __tablename__ = "heat_inputs"

    heat_id: Mapped[int] = mapped_column(
        ForeignKey("heats.id", ondelete="CASCADE"), primary_key=True
    )
    lot_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_lots.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
    kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    heat: Mapped[Heat] = relationship(back_populates="inputs")
    lot: Mapped[PurchaseLot] = relationship(back_populates="inputs")

    __table_args__ = (CheckConstraint("kg > 0", name="kg_positive"),)
