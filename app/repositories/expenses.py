"""Monthly expenses repository."""

from __future__ import annotations

from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.expense import MonthlyExpense


class ExpenseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, month: str | None = None) -> list[MonthlyExpense]:
        statement = select(MonthlyExpense)
        if month:
            statement = statement.where(MonthlyExpense.month == month)
        statement = statement.order_by(MonthlyExpense.month.desc(), MonthlyExpense.id)
        return list(self.session.scalars(statement).all())

    def get(self, expense_id: int) -> MonthlyExpense | None:
        return self.session.get(MonthlyExpense, expense_id)

    def add(self, expense: MonthlyExpense) -> None:
        self.session.add(expense)

    def delete(self, expense: MonthlyExpense) -> None:
        self.session.delete(expense)

    def total_for_month(self, month: str) -> Decimal:
        statement = select(func.coalesce(func.sum(MonthlyExpense.amount), Decimal("0.00"))).where(
            MonthlyExpense.month == month
        )
        return self.session.scalar(statement) or Decimal("0.00")

