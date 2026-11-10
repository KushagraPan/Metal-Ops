"""Heat queries and persistence."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Alloy,
    Heat,
    HeatInput,
    PurchaseLot,
    ReportResult,
    SpectroReport,
)


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


class HeatRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _dialect(self) -> str:
        return self.session.get_bind().dialect.name

    def begin_write(self) -> None:
        """Take SQLite's write lock before reading stock.

        SQLite only serialises writes at the moment a write starts. Starting
        the transaction with `BEGIN IMMEDIATE` makes the stock read and the
        later insert one serialised unit, so two creates cannot both pass the
        same availability check. PostgreSQL uses row locks in `get_lots`.
        """
        if self._dialect() == "sqlite" and not self.session.in_transaction():
            self.session.execute(text("BEGIN IMMEDIATE"))

    def list(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        alloy: Alloy | None = None,
        report_result: ReportResult | None = None,
        heat_no: str | None = None,
    ) -> list[Heat]:
        statement = (
            select(Heat)
            .options(
                selectinload(Heat.inputs).selectinload(HeatInput.lot),
                selectinload(Heat.sales),
                selectinload(Heat.reports),
            )
            .order_by(Heat.heat_date.desc(), Heat.id.desc())
        )
        if from_date is not None:
            statement = statement.where(Heat.heat_date >= from_date)
        if to_date is not None:
            statement = statement.where(Heat.heat_date <= to_date)
        if alloy is not None:
            statement = statement.where(Heat.alloy == alloy)
        if report_result is not None:
            statement = statement.where(
                Heat.reports.any(SpectroReport.result == report_result)
            )
        if heat_no is not None and heat_no.strip():
            escaped = (
                heat_no.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            statement = statement.where(
                Heat.heat_no.ilike(f"%{escaped}%", escape="\\")
            )
        return list(self.session.scalars(statement).unique())

    def get(self, heat_id: int, *, for_update: bool = False) -> Heat | None:
        statement = (
            select(Heat)
            .options(
                selectinload(Heat.inputs).selectinload(HeatInput.lot),
                selectinload(Heat.sales),
                selectinload(Heat.reports),
            )
            .where(Heat.id == heat_id)
        )
        if for_update and self._dialect() != "sqlite":
            statement = statement.with_for_update()
        return self.session.scalars(statement).unique().first()

    def get_by_heat_no(self, heat_no: str) -> Heat | None:
        return self.session.scalars(
            select(Heat).where(Heat.heat_no == heat_no)
        ).first()

    def get_lots(
        self, lot_ids: list[int], *, for_update: bool = False
    ) -> list[PurchaseLot]:
        if not lot_ids:
            return []
        statement = select(PurchaseLot).where(PurchaseLot.id.in_(lot_ids))
        if for_update and self._dialect() != "sqlite":
            statement = statement.with_for_update()
        return list(self.session.scalars(statement).all())

    def consumed_by_lots(
        self,
        lot_ids: list[int],
        *,
        exclude_heat_id: int | None = None,
    ) -> dict[int, Decimal]:
        if not lot_ids:
            return {}
        statement = (
            select(
                HeatInput.lot_id,
                func.coalesce(func.sum(HeatInput.kg), 0),
            )
            .where(HeatInput.lot_id.in_(lot_ids))
            .group_by(HeatInput.lot_id)
        )
        if exclude_heat_id is not None:
            statement = statement.where(HeatInput.heat_id != exclude_heat_id)
        return {
            lot_id: _decimal(value)
            for lot_id, value in self.session.execute(statement).all()
        }

    def add(self, heat: Heat) -> None:
        self.session.add(heat)

    def delete(self, heat: Heat) -> None:
        self.session.delete(heat)
