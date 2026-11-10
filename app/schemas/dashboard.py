"""Dashboard request and response schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import Alloy
from app.schemas.expenses import ExpenseRead


class GstSummaryRead(BaseModel):
    collected: Decimal
    credit: Decimal
    net_payable_estimate: Decimal


class DashboardHeatSummary(BaseModel):
    id: int
    heat_no: str
    heat_date: date
    alloy: Alloy
    output_kg: Decimal
    yield_pct: Decimal | None
    heat_profit: Decimal | None
    is_provisional: bool


class DashboardRead(BaseModel):
    month: str
    revenue: Decimal
    profit: Decimal
    is_provisional: bool
    heats_count: int
    average_yield_pct: Decimal | None
    planned_yield_pct: Decimal
    yield_diff_pct: Decimal | None
    break_even_heats: Decimal | None
    expenses_total: Decimal
    gst_estimate: GstSummaryRead
    heats: list[DashboardHeatSummary]
    expenses: list[ExpenseRead]

