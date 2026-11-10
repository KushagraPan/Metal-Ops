"""Dashboard aggregation service using pure calculations from app/calc."""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calc import (
    break_even_heats,
    gst_summary,
    monthly_is_provisional,
    monthly_profit,
    net_outbound_transport,
    sale_revenue,
    yield_pct,
)
from app.models import PurchaseLot, Sale
from app.repositories.expenses import ExpenseRepository
from app.repositories.settings import SettingsRepository
from app.schemas.dashboard import (
    DashboardHeatSummary,
    DashboardRead,
    GstSummaryRead,
)
from app.schemas.expenses import ExpenseRead
from app.services.heats import HeatService

MONTH_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
DEFAULT_GST_RATE = Decimal("0.18")
DEFAULT_PLANNED_YIELD = Decimal("89.00")


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.heats_service = HeatService(session)
        self.expenses_repo = ExpenseRepository(session)
        self.settings_repo = SettingsRepository(session)

    def get_dashboard(self, month: str) -> DashboardRead:
        if not MONTH_REGEX.match(month):
            raise ValueError(f"invalid month format: {month!r}, expected YYYY-MM")

        year, month_num = map(int, month.split("-"))
        _, last_day = calendar.monthrange(year, month_num)
        start_date = date(year, month_num, 1)
        end_date = date(year, month_num, last_day)

        # 1. Heats dated in the month
        heat_views = self.heats_service.list(from_date=start_date, to_date=end_date)

        # 2. Sales in the month
        sales_stmt = select(Sale).where(
            Sale.sale_date >= start_date, Sale.sale_date <= end_date
        )
        sales = list(self.session.scalars(sales_stmt).all())

        # 3. Purchases in the month
        purchases_stmt = select(PurchaseLot).where(
            PurchaseLot.purchase_date >= start_date,
            PurchaseLot.purchase_date <= end_date,
        )
        purchases = list(self.session.scalars(purchases_stmt).all())

        # 4. Expenses for the month
        expenses = self.expenses_repo.list(month=month)
        expenses_total = sum((e.amount for e in expenses), Decimal("0.00"))

        # 5. Settings
        settings = self.settings_repo.get()
        gst_rate = settings.gst_rate if settings else DEFAULT_GST_RATE
        planned_yield_pct = (
            settings.planned_yield_pct if settings else DEFAULT_PLANNED_YIELD
        )

        # Calculations
        heat_profits = [
            h.heat_profit for h in heat_views if h.heat_profit is not None
        ]

        # Unlinked sales dated in the month
        unlinked_sales = [s for s in sales if s.heat_id is None]
        unlinked_sale_profits = [
            sale_revenue(s.weight_kg, s.rate_per_kg)
            - net_outbound_transport(
                s.transport_mode.value, s.transport_cost, s.transport_billed
            )
            for s in unlinked_sales
        ]
        unlinked_revenue = sum(
            (sale_revenue(s.weight_kg, s.rate_per_kg) for s in unlinked_sales),
            Decimal("0.00"),
        )

        monthly_rev = sum(
            (h.revenue for h in heat_views), Decimal("0.00")
        ) + unlinked_revenue

        profit = monthly_profit(
            heat_profits,
            unlinked_sale_profits,
            [e.amount for e in expenses],
        )

        is_provisional_flag = monthly_is_provisional(
            [h.is_provisional for h in heat_views]
        )

        break_even = break_even_heats(expenses_total, heat_profits)

        # GST summary
        sales_gst_tuples = [
            (s.weight_kg, s.rate_per_kg, s.gst_mode.value) for s in sales
        ]
        purchases_gst_tuples = [
            (p.weight_kg, p.rate_per_kg, p.gst_mode.value) for p in purchases
        ]
        gst = gst_summary(sales_gst_tuples, purchases_gst_tuples, gst_rate)

        # Yield
        total_output = sum(
            (h.heat.output_kg for h in heat_views if h.total_input_kg > 0),
            Decimal("0.00"),
        )
        total_input = sum(
            (h.total_input_kg for h in heat_views if h.total_input_kg > 0),
            Decimal("0.00"),
        )
        average_yield = yield_pct(total_output, total_input) if total_input > 0 else None
        yield_diff = (
            (average_yield - planned_yield_pct).quantize(Decimal("0.01"))
            if average_yield is not None
            else None
        )

        heat_summaries = [
            DashboardHeatSummary(
                id=h.heat.id,
                heat_no=h.heat.heat_no,
                heat_date=h.heat.heat_date,
                alloy=h.heat.alloy,
                output_kg=h.heat.output_kg,
                yield_pct=h.yield_pct,
                heat_profit=h.heat_profit,
                is_provisional=h.is_provisional,
            )
            for h in heat_views
        ]

        expense_reads = [
            ExpenseRead(
                id=e.id,
                month=e.month,
                category=e.category,
                amount=e.amount,
            )
            for e in expenses
        ]

        return DashboardRead(
            month=month,
            revenue=monthly_rev,
            profit=profit,
            is_provisional=is_provisional_flag,
            heats_count=len(heat_views),
            average_yield_pct=average_yield,
            planned_yield_pct=planned_yield_pct,
            yield_diff_pct=yield_diff,
            break_even_heats=break_even,
            expenses_total=expenses_total,
            gst_estimate=GstSummaryRead(
                collected=gst["collected"],
                credit=gst["credit"],
                net_payable_estimate=gst["net_payable_estimate"],
            ),
            heats=heat_summaries,
            expenses=expense_reads,
        )

