"""Monthly expense service and business rules."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.expense import MonthlyExpense
from app.repositories.expenses import ExpenseRepository
from app.schemas.expenses import ExpenseCreate, ExpenseUpdate


class ExpenseError(Exception):
    pass


class ExpenseNotFound(ExpenseError):
    pass


class ExpenseValidationError(ExpenseError):
    pass


class ExpenseService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.expenses = ExpenseRepository(session)

    def list(self, month: str | None = None) -> list[MonthlyExpense]:
        return self.expenses.list(month)

    def get(self, expense_id: int) -> MonthlyExpense:
        expense = self.expenses.get(expense_id)
        if expense is None:
            raise ExpenseNotFound(f"expense {expense_id} not found")
        return expense

    def create(self, data: ExpenseCreate) -> MonthlyExpense:
        expense = MonthlyExpense(
            month=data.month,
            category=data.category,
            amount=data.amount,
        )
        self.expenses.add(expense)
        self.session.commit()
        return expense

    def update(self, expense_id: int, data: ExpenseUpdate) -> MonthlyExpense:
        expense = self.get(expense_id)
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(expense, field, value)
        self.session.commit()
        return expense

    def delete(self, expense_id: int) -> None:
        expense = self.get(expense_id)
        self.expenses.delete(expense)
        self.session.commit()

