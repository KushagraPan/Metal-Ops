from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session, make_engine
from app.main import app
from app.models import (
    Alloy,
    Base,
    GstMode,
    Heat,
    HeatInput,
    ItemType,
    MonthlyExpense,
    PurchaseLot,
    PurchaseTransportMode,
    Sale,
    SaleTransportMode,
    Setting,
)
from app.seed import seed
from app.storage import LocalStorage

D = Decimal


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = make_engine(f"sqlite:///{(tmp_path / 'dashboard.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
) -> Iterator[TestClient]:
    def override_get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_dashboard_with_seed_data_for_october_2026(
    client: TestClient,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    storage = LocalStorage(tmp_path / "storage")
    with session_factory() as session:
        seed(session, storage=storage)

    response = client.get("/api/dashboard", params={"month": "2026-10"})
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["month"] == "2026-10"
    assert data["revenue"] == "831370.00"
    assert data["profit"] == "-639530.00"
    assert data["heats_count"] == 3
    assert data["is_provisional"] is True
    assert data["break_even_heats"] is None  # negative average heat profit
    assert data["planned_yield_pct"] == "89.00"
    assert data["average_yield_pct"] is not None

    gst = data["gst_estimate"]
    assert gst["collected"] == "111195.00"
    assert gst["credit"] == "90720.00"
    assert gst["net_payable_estimate"] == "20475.00"

    assert data["expenses_total"] == "173000.00"
    assert len(data["expenses"]) == 3
    assert len(data["heats"]) == 3


def test_month_selector_changes_all_figures(
    client: TestClient,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    storage = LocalStorage(tmp_path / "storage")
    with session_factory() as session:
        seed(session, storage=storage)

    # Empty month
    empty_res = client.get("/api/dashboard", params={"month": "2026-08"})
    assert empty_res.status_code == 200
    empty_data = empty_res.json()
    assert empty_data["month"] == "2026-08"
    assert empty_data["revenue"] == "0.00"
    assert empty_data["profit"] == "0.00"
    assert empty_data["heats_count"] == 0
    assert empty_data["is_provisional"] is False
    assert empty_data["break_even_heats"] is None
    assert empty_data["gst_estimate"]["collected"] == "0.00"
    assert empty_data["gst_estimate"]["credit"] == "0.00"
    assert empty_data["gst_estimate"]["net_payable_estimate"] == "0.00"
    assert empty_data["expenses_total"] == "0.00"
    assert empty_data["heats"] == []
    assert empty_data["expenses"] == []


def test_break_even_calculated_when_heat_profit_positive(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(Setting(id=1, gst_rate=D("0.18"), planned_yield_pct=D("89.00")))
        lot = PurchaseLot(
            purchase_date=date(2026, 11, 1),
            supplier="Demo",
            notes=None,
            weight_kg=D("1000.00"),
            rate_per_kg=D("200.00"),
            gst_mode=GstMode.WITHOUT,
            transport_mode=PurchaseTransportMode.SUPPLIER_DELIVERS,
            transport_cost=D("0.00"),
        )
        session.add(lot)
        session.flush()

        heat = Heat(
            heat_no="H-NOV-1",
            heat_date=date(2026, 11, 2),
            duration_hours=None,
            alloy=Alloy.ADC12,
            output_kg=D("890.00"),
            dross_kg=D("0.00"),
            iron_scrap_kg=D("0.00"),
            oil_cost=D("0.00"),
            power_cost=D("0.00"),
            labour_cost=D("0.00"),
            other_cost=D("0.00"),
        )
        session.add(heat)
        session.flush()

        session.add(HeatInput(heat_id=heat.id, lot_id=lot.id, kg=D("1000.00")))

        # Revenue = 890 * 250 = 222,500. Scrap = 200,000. Heat profit = 22,500.00
        sale = Sale(
            sale_date=date(2026, 11, 3),
            customer="Client",
            item_type=ItemType.ADC12,
            heat_id=heat.id,
            weight_kg=D("890.00"),
            rate_per_kg=D("250.00"),
            gst_mode=GstMode.WITHOUT,
            transport_mode=SaleTransportMode.CUSTOMER_ARRANGES,
            transport_cost=D("0.00"),
            transport_billed=D("0.00"),
        )
        session.add(sale)

        # Monthly expenses = 45,000.00
        session.add(
            MonthlyExpense(month="2026-11", category="Rent", amount=D("45000.00"))
        )
        session.commit()

    res = client.get("/api/dashboard", params={"month": "2026-11"})
    assert res.status_code == 200
    data = res.json()
    assert data["revenue"] == "222500.00"
    # profit = 22,500 - 45,000 = -22,500.00
    assert data["profit"] == "-22500.00"
    # average heat profit = 22,500.00 > 0.
    # break_even_heats = 45,000 / 22,500 = 2.00
    assert data["break_even_heats"] == "2.00"
    # heat is fully sold (890 == 890), so provisional is False
    assert data["is_provisional"] is False


def test_unlinked_sale_included_in_monthly_profit_and_revenue(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(Setting(id=1, gst_rate=D("0.18"), planned_yield_pct=D("89.00")))
        # Unlinked dross sale in 2026-12
        sale = Sale(
            sale_date=date(2026, 12, 10),
            customer="Scrap Dealer",
            item_type=ItemType.DROSS,
            heat_id=None,
            weight_kg=D("100.00"),
            rate_per_kg=D("50.00"),
            gst_mode=GstMode.WITH,
            transport_mode=SaleTransportMode.WE_PAY_ABSORB,
            transport_cost=D("200.00"),
            transport_billed=D("0.00"),
        )
        session.add(sale)
        session.commit()

    res = client.get("/api/dashboard", params={"month": "2026-12"})
    assert res.status_code == 200
    data = res.json()
    # Revenue = 100 * 50 = 5000.00
    assert data["revenue"] == "5000.00"
    # Profit = 5000 - 200 (net transport) = 4800.00
    assert data["profit"] == "4800.00"
    assert data["heats_count"] == 0
    # GST collected = 5000 * 0.18 = 900.00
    assert data["gst_estimate"]["collected"] == "900.00"
