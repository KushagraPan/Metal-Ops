"""Pure calculation functions for rules R2 to R12.

This module must never import the database, HTTP or a model. Money and weights
are `Decimal`; values are quantized to two decimal places at the public
boundary.

GST and transport modes are plain strings, matching the enum values stored by
the data model, so this module stays independent of SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

MONEY = Decimal("0.01")
PERCENT = Decimal("0.01")

GST_WITH = "WITH"
GST_WITHOUT = "WITHOUT"

PURCHASE_SUPPLIER_DELIVERS = "SUPPLIER_DELIVERS"
PURCHASE_WE_PAY = "WE_PAY"

SALE_CUSTOMER_ARRANGES = "CUSTOMER_ARRANGES"
SALE_WE_PAY_ABSORB = "WE_PAY_ABSORB"
SALE_WE_PAY_BILL = "WE_PAY_BILL"


def _number(value: Decimal | int | str, field: str) -> Decimal:
    """Coerce a numeric value, rejecting `float` to keep money exact."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError(f"{field} must be Decimal, int or str, not bool")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value)
    raise TypeError(
        f"{field} must be Decimal, int or str, not {type(value).__name__}"
    )


def _mode(value: object) -> str:
    """Return the string value of a mode, accepting a StrEnum as well."""
    return str(getattr(value, "value", value))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT, rounding=ROUND_HALF_UP)


def gst_amount(
    weight_kg: Decimal | int | str,
    rate_per_kg: Decimal | int | str,
    gst_rate: Decimal | int | str,
    gst_mode: str,
) -> Decimal:
    """R2: GST on `weight * rate` when mode is WITH; zero otherwise.

    The base excludes inbound transport.
    """
    weight = _number(weight_kg, "weight_kg")
    rate = _number(rate_per_kg, "rate_per_kg")
    percentage = _number(gst_rate, "gst_rate")
    mode = _mode(gst_mode)

    if mode == GST_WITHOUT:
        return _money(Decimal("0"))
    if mode != GST_WITH:
        raise ValueError(f"unknown GST mode: {gst_mode!r}")
    return _money(weight * rate * percentage)


def landed_cost_per_kg(
    weight_kg: Decimal | int | str,
    rate_per_kg: Decimal | int | str,
    transport_cost: Decimal | int | str,
    transport_mode: str,
) -> Decimal | None:
    """R3: purchase cost per kg including inbound freight, excluding GST.

    Returns `None` when the weight is zero or negative, because the division
    has no business meaning.
    """
    weight = _number(weight_kg, "weight_kg")
    if weight <= 0:
        return None

    rate = _number(rate_per_kg, "rate_per_kg")
    transport = _number(transport_cost, "transport_cost")
    mode = _mode(transport_mode)

    if mode == PURCHASE_WE_PAY:
        freight = transport
    elif mode == PURCHASE_SUPPLIER_DELIVERS:
        freight = Decimal("0")
    else:
        raise ValueError(
            f"unknown purchase transport mode: {transport_mode!r}"
        )

    return _money((weight * rate + freight) / weight)


def heat_scrap_cost(
    inputs: Iterable[tuple[Decimal | int | str, Decimal | int | str]],
) -> Decimal:
    """R7: sum of `kg * landed_cost_per_kg` for every lot used by a heat.

    Each pair is `(kg, landed_cost_per_kg)`.
    """
    total = Decimal("0")
    for kg, landed_cost in inputs:
        total += _number(kg, "kg") * _number(
            landed_cost, "landed_cost_per_kg"
        )
    return _money(total)


def yield_pct(
    output_kg: Decimal | int | str,
    total_input_kg: Decimal | int | str,
) -> Decimal | None:
    """R5: `output / input * 100`, or `None` when input is non-positive."""
    output = _number(output_kg, "output_kg")
    total_input = _number(total_input_kg, "total_input_kg")
    if total_input <= 0:
        return None
    return _percent(output / total_input * Decimal("100"))


def net_outbound_transport(
    transport_mode: str,
    transport_cost: Decimal | int | str,
    transport_billed: Decimal | int | str,
) -> Decimal:
    """R6: the freight cost a sale adds to the heat's profit.

    - CUSTOMER_ARRANGES: 0
    - WE_PAY_ABSORB: the cost we pay
    - WE_PAY_BILL: the cost we pay minus what we bill the customer
    """
    mode = _mode(transport_mode)
    cost = _number(transport_cost, "transport_cost")
    billed = _number(transport_billed, "transport_billed")

    if mode == SALE_CUSTOMER_ARRANGES:
        return _money(Decimal("0"))
    if mode == SALE_WE_PAY_ABSORB:
        return _money(cost)
    if mode == SALE_WE_PAY_BILL:
        return _money(cost - billed)
    raise ValueError(f"unknown sale transport mode: {transport_mode!r}")


def heat_profit(
    revenue: Decimal | int | str,
    scrap_cost: Decimal | int | str,
    variable_costs: Decimal | int | str,
    net_transport: Decimal | int | str,
) -> Decimal:
    """R7: revenue minus scrap, variable costs and net outbound transport."""
    return _money(
        _number(revenue, "revenue")
        - _number(scrap_cost, "scrap_cost")
        - _number(variable_costs, "variable_costs")
        - _number(net_transport, "net_transport")
    )


def is_provisional(
    sold_alloy_kg: Decimal | int | str,
    output_kg: Decimal | int | str,
) -> bool:
    """R8: a heat is provisional while sold alloy kg is below output kg."""
    return _number(sold_alloy_kg, "sold_alloy_kg") < _number(
        output_kg, "output_kg"
    )


def monthly_profit(
    heat_profits: Iterable[Decimal | int | str],
    unlinked_sale_profits: Iterable[Decimal | int | str],
    monthly_expenses: Iterable[Decimal | int | str],
) -> Decimal:
    """R10: heat profits plus unlinked byproduct sales minus fixed expenses."""
    total = sum(
        (_number(value, "heat_profit") for value in heat_profits),
        Decimal("0"),
    )
    total += sum(
        (
            _number(value, "unlinked_sale_profit")
            for value in unlinked_sale_profits
        ),
        Decimal("0"),
    )
    total -= sum(
        (_number(value, "monthly_expense") for value in monthly_expenses),
        Decimal("0"),
    )
    return _money(total)


def break_even_heats(
    monthly_expenses: Decimal | int | str,
    heat_profits: Iterable[Decimal | int | str],
) -> Decimal | None:
    """R11: `expenses / average_heat_profit`, or `None` when undefined.

    `None` covers no heats, a zero average and a negative average. The UI
    renders it as `n/a`.
    """
    profits = [_number(value, "heat_profit") for value in heat_profits]
    if not profits:
        return None

    average = sum(profits, Decimal("0")) / len(profits)
    if average <= 0:
        return None

    expenses = _number(monthly_expenses, "monthly_expenses")
    return _money(expenses / average)


def gst_summary(
    sales: Iterable[tuple[Decimal | int | str, Decimal | int | str, str]],
    purchases: Iterable[tuple[Decimal | int | str, Decimal | int | str, str]],
    gst_rate: Decimal | int | str,
) -> dict[str, Decimal]:
    """R12: monthly GST collected, credit and net payable estimate.

    Each sale or purchase is `(weight_kg, rate_per_kg, gst_mode)`. Transport is
    excluded from the GST base.
    """
    collected = sum(
        (
            gst_amount(weight, rate, gst_rate, mode)
            for weight, rate, mode in sales
        ),
        Decimal("0"),
    )
    credit = sum(
        (
            gst_amount(weight, rate, gst_rate, mode)
            for weight, rate, mode in purchases
        ),
        Decimal("0"),
    )
    return {
        "collected": _money(collected),
        "credit": _money(credit),
        "net_payable_estimate": _money(collected - credit),
    }
