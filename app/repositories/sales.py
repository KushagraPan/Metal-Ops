"""Sale queries and persistence."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import ItemType, Sale


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


class SaleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _dialect(self) -> str:
        return self.session.get_bind().dialect.name

    def begin_write(self) -> None:
        """Serialise the alloy cap check with the sale write on SQLite."""
        if self._dialect() == "sqlite" and not self.session.in_transaction():
            self.session.execute(text("BEGIN IMMEDIATE"))

    def list(self) -> list[Sale]:
        statement = select(Sale).order_by(Sale.sale_date.desc(), Sale.id.desc())
        return list(self.session.scalars(statement).all())

    def get(self, sale_id: int, *, for_update: bool = False) -> Sale | None:
        statement = select(Sale).where(Sale.id == sale_id)
        if for_update and self._dialect() != "sqlite":
            statement = statement.with_for_update()
        return self.session.scalars(statement).first()

    def sold_alloy_kg(
        self, heat_id: int, *, exclude_sale_id: int | None = None
    ) -> Decimal:
        statement = select(
            func.coalesce(func.sum(Sale.weight_kg), 0)
        ).where(
            Sale.heat_id == heat_id,
            Sale.item_type.in_([ItemType.ADC12, ItemType.LM6]),
        )
        if exclude_sale_id is not None:
            statement = statement.where(Sale.id != exclude_sale_id)
        return _decimal(self.session.scalar(statement))

    def add(self, sale: Sale) -> None:
        self.session.add(sale)

    def delete(self, sale: Sale) -> None:
        self.session.delete(sale)
