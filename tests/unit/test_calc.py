from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from app.calc import (
    break_even_heats,
    gst_amount,
    gst_summary,
    heat_profit,
    heat_scrap_cost,
    is_provisional,
    landed_cost_per_kg,
    monthly_profit,
    net_outbound_transport,
    yield_pct,
)

D = Decimal
GST = D("0.18")
ROOT = Path(__file__).resolve().parents[2]


def test_gst_amount_with_and_without_gst() -> None:
    assert gst_amount(D("1000"), D("200"), GST, "WITH") == D("36000.00")
    assert gst_amount(D("1000"), D("200"), GST, "WITHOUT") == D("0.00")


def test_gst_amount_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        gst_amount(D("1000"), D("200"), GST, "SOMETIMES")


def test_worked_example_landed_cost() -> None:
    assert (
        landed_cost_per_kg(D("1000"), D("200"), D("2000"), "WE_PAY")
        == D("202.00")
    )


def test_landed_cost_ignores_transport_when_supplier_delivers() -> None:
    assert (
        landed_cost_per_kg(
            D("1000"), D("200"), D("2000"), "SUPPLIER_DELIVERS"
        )
        == D("200.00")
    )


@pytest.mark.parametrize("weight", [D("0"), D("-1")])
def test_landed_cost_returns_none_for_non_positive_weight(weight: Decimal) -> None:
    assert landed_cost_per_kg(weight, D("200"), D("2000"), "WE_PAY") is None


def test_heat_scrap_cost_sums_kg_times_landed_cost() -> None:
    assert (
        heat_scrap_cost([(D("1000"), D("202.00"))]) == D("202000.00")
    )
    assert (
        heat_scrap_cost(
            [(D("600"), D("202.00")), (D("400"), D("210.00"))]
        )
        == D("205200.00")
    )
    assert heat_scrap_cost([]) == D("0.00")


def test_worked_example_yield() -> None:
    assert yield_pct(D("890"), D("1000")) == D("89.00")


@pytest.mark.parametrize("total_input_kg", [D("0"), D("-10")])
def test_yield_returns_none_for_non_positive_input(
    total_input_kg: Decimal,
) -> None:
    assert yield_pct(D("890"), total_input_kg) is None


def test_yield_rounds_to_two_decimals() -> None:
    assert yield_pct(D("1"), D("3")) == D("33.33")


@pytest.mark.parametrize(
    ("mode", "cost", "billed", "expected"),
    [
        ("CUSTOMER_ARRANGES", D("3000"), D("2000"), D("0.00")),
        ("WE_PAY_ABSORB", D("3000"), D("2000"), D("3000.00")),
        ("WE_PAY_BILL", D("3000"), D("2000"), D("1000.00")),
    ],
)
def test_net_outbound_transport_for_every_mode(
    mode: str, cost: Decimal, billed: Decimal, expected: Decimal
) -> None:
    assert net_outbound_transport(mode, cost, billed) == expected


def test_net_outbound_transport_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        net_outbound_transport("SOMETIMES", D("3000"), D("2000"))


def test_worked_example_profit_with_absorbed_freight() -> None:
    profit = heat_profit(
        revenue=D("219160"),
        scrap_cost=D("202000"),
        variable_costs=D("11000"),
        net_transport=net_outbound_transport(
            "WE_PAY_ABSORB", D("3000"), D("0")
        ),
    )
    assert profit == D("3160.00")


def test_worked_example_profit_with_billed_freight() -> None:
    profit = heat_profit(
        revenue=D("219160"),
        scrap_cost=D("202000"),
        variable_costs=D("11000"),
        net_transport=net_outbound_transport(
            "WE_PAY_BILL", D("3000"), D("2000")
        ),
    )
    assert profit == D("5160.00")


def test_heat_profit_can_be_negative() -> None:
    profit = heat_profit(
        revenue=D("100"),
        scrap_cost=D("200"),
        variable_costs=D("50"),
        net_transport=D("10"),
    )
    assert profit == D("-160.00")


def test_gst_mode_never_changes_profit() -> None:
    with_gst = gst_amount(D("1000"), D("200"), GST, "WITH")
    without_gst = gst_amount(D("1000"), D("200"), GST, "WITHOUT")
    assert with_gst != without_gst

    landed = [
        landed_cost_per_kg(D("1000"), D("200"), D("2000"), "WE_PAY"),
        landed_cost_per_kg(D("1000"), D("200"), D("2000"), "WE_PAY"),
    ]
    scrap = heat_scrap_cost([(D("1000"), landed[0])])
    net = net_outbound_transport("WE_PAY_ABSORB", D("3000"), D("0"))

    profits = [
        heat_profit(D("219160"), scrap, D("11000"), net),
        heat_profit(D("219160"), scrap, D("11000"), net),
    ]
    assert profits == [D("3160.00"), D("3160.00")]


@pytest.mark.parametrize(
    ("sold", "output", "expected"),
    [
        (D("0"), D("890"), True),
        (D("889"), D("890"), True),
        (D("890"), D("890"), False),
        (D("891"), D("890"), False),
    ],
)
def test_is_provisional(
    sold: Decimal, output: Decimal, expected: bool
) -> None:
    assert is_provisional(sold, output) is expected


def test_monthly_profit_sums_heats_sales_and_expenses() -> None:
    assert (
        monthly_profit(
            heat_profits=[D("3160.00"), D("1000.00")],
            unlinked_sale_profits=[D("500.00"), D("160.00")],
            monthly_expenses=[D("1000.00"), D("200.00")],
        )
        == D("3620.00")
    )


def test_monthly_profit_with_no_data_is_zero() -> None:
    assert monthly_profit([], [], []) == D("0.00")


def test_monthly_profit_can_be_negative() -> None:
    assert (
        monthly_profit([D("100")], [], [D("500")]) == D("-400.00")
    )


def test_break_even_heats_uses_average_profit() -> None:
    assert (
        break_even_heats(D("10000"), [D("1000"), D("2000"), D("3000")])
        == D("5.00")
    )


def test_break_even_heats_rounds_to_two_decimals() -> None:
    assert break_even_heats(D("10000"), [D("3000")]) == D("3.33")


def test_break_even_heats_returns_none_without_heats() -> None:
    assert break_even_heats(D("10000"), []) is None


@pytest.mark.parametrize(
    "heat_profits",
    [
        [D("1000"), D("-1000")],
        [D("100"), D("-200")],
        [D("-100")],
    ],
)
def test_break_even_heats_returns_none_for_non_positive_average(
    heat_profits: list[Decimal],
) -> None:
    assert break_even_heats(D("10000"), heat_profits) is None


def test_break_even_heats_with_zero_expenses() -> None:
    assert break_even_heats(D("0"), [D("1000")]) == D("0.00")


def test_gst_summary_collects_and_credits_only_with_gst() -> None:
    summary = gst_summary(
        sales=[
            (D("890"), D("240"), "WITH"),
            (D("60"), D("90"), "WITHOUT"),
        ],
        purchases=[
            (D("1000"), D("200"), "WITH"),
            (D("500"), D("100"), "WITHOUT"),
        ],
        gst_rate=GST,
    )
    assert summary == {
        "collected": D("38448.00"),
        "credit": D("36000.00"),
        "net_payable_estimate": D("2448.00"),
    }


def test_gst_summary_with_no_entries_is_zero() -> None:
    assert gst_summary([], [], GST) == {
        "collected": D("0.00"),
        "credit": D("0.00"),
        "net_payable_estimate": D("0.00"),
    }


def test_calc_rejects_float_inputs() -> None:
    with pytest.raises(TypeError):
        gst_amount(1000.0, D("200"), GST, "WITH")
    with pytest.raises(TypeError):
        landed_cost_per_kg(1000.0, D("200"), D("2000"), "WE_PAY")


def test_calc_imports_no_database_or_http_modules() -> None:
    tree = ast.parse((ROOT / "app" / "calc.py").read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)

    assert modules <= {"__future__", "collections.abc", "decimal", "typing"}
