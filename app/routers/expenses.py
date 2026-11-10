"""Monthly expense HTTP endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.expense import MonthlyExpense
from app.schemas.expenses import ExpenseCreate, ExpenseRead, ExpenseUpdate
from app.services.expenses import ExpenseNotFound, ExpenseService, ExpenseValidationError

router = APIRouter(prefix="/expenses", tags=["expenses"])
SessionDep = Annotated[Session, Depends(get_session)]


def expense_to_read(expense: MonthlyExpense) -> ExpenseRead:
    return ExpenseRead(
        id=expense.id,
        month=expense.month,
        category=expense.category,
        amount=expense.amount,
    )


@router.get("", response_model=list[ExpenseRead])
def list_expenses(session: SessionDep, month: str | None = None) -> list[ExpenseRead]:
    expenses = ExpenseService(session).list(month=month)
    return [expense_to_read(e) for e in expenses]


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(data: ExpenseCreate, session: SessionDep) -> ExpenseRead:
    try:
        expense = ExpenseService(session).create(data)
        return expense_to_read(expense)
    except ExpenseValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.get("/{expense_id}", response_model=ExpenseRead)
def get_expense(expense_id: int, session: SessionDep) -> ExpenseRead:
    try:
        expense = ExpenseService(session).get(expense_id)
        return expense_to_read(expense)
    except ExpenseNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error


@router.put("/{expense_id}", response_model=ExpenseRead)
def update_expense(
    expense_id: int, data: ExpenseUpdate, session: SessionDep
) -> ExpenseRead:
    try:
        expense = ExpenseService(session).update(expense_id, data)
        return expense_to_read(expense)
    except ExpenseNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except ExpenseValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: int, session: SessionDep) -> Response:
    try:
        ExpenseService(session).delete(expense_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ExpenseNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error

