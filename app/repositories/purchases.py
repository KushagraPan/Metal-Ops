"""Purchase lot queries and persistence."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import HeatInput, PurchaseLot


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


class PurchaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_with_consumed(self) -> list[tuple[PurchaseLot, Decimal]]:
        """Return lots with their consumed kilograms in one query."""
        consumed = func.coalesce(func.sum(HeatInput.kg), 0)
        statement = (
            select(PurchaseLot, consumed)
            .outerjoin(HeatInput, HeatInput.lot_id == PurchaseLot.id)
            .group_by(PurchaseLot.id)
            .order_by(
                PurchaseLot.purchase_date.desc(), PurchaseLot.id.desc()
            )
        )
        return [
            (lot, _decimal(value))
            for lot, value in self.session.execute(statement).all()
        ]

    def get(self, lot_id: int) -> PurchaseLot | None:
        return self.session.get(PurchaseLot, lot_id)

    def consumed_kg(self, lot_id: int) -> Decimal:
        value = self.session.scalar(
            select(func.coalesce(func.sum(HeatInput.kg), 0)).where(
                HeatInput.lot_id == lot_id
            )
        )
        return _decimal(value)

    def add(self, lot: PurchaseLot) -> None:
        self.session.add(lot)

    def delete(self, lot: PurchaseLot) -> None:
        self.session.delete(lot)
