"""PostgreSQL concurrency tests using row-level locking (FOR UPDATE).

Acceptance criteria:
- The race: two real concurrent requests (threads with a barrier, separate connections)
  against Postgres; exactly one create succeeds, the other returns 422, remaining stock
  ends at 0.00, never negative.
- Same race for sales against the sold-alloy cap.
- Proves that the FOR UPDATE row locking guarantees serialized atomicity on PostgreSQL.
"""

from __future__ import annotations

import threading
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Heat, HeatInput, PurchaseLot, Sale
from app.schemas.heats import HeatInputPayload, HeatWrite
from app.schemas.sales import SaleWrite
from app.services.heats import HeatError, HeatService, HeatStockError
from app.services.sales import SaleError, SaleService, SaleValidationError


pytestmark = pytest.mark.integration


def test_concurrent_heat_creation_race_api(
    auth_client: TestClient,
    postgres_session_factory: sessionmaker[Session],
) -> None:
    """Two concurrent requests race to consume the same remaining 500 kg stock.

    With row-level locking (FOR UPDATE) in PostgreSQL:
    - Exactly one request succeeds (201).
    - Exactly one request fails (422: insufficient stock).
    - Remaining stock ends at exactly 0.00, never negative.
    """
    # 1. Create a lot with 500 kg
    lot_res = auth_client.post(
        "/api/purchases",
        json={
            "purchase_date": "2026-10-20",
            "supplier": "Concurrent Scrap Co",
            "weight_kg": 500.00,
            "rate_per_kg": 200.00,
            "gst_mode": "WITH",
            "transport_mode": "SUPPLIER_DELIVERS",
            "transport_cost": 0.00,
        },
    )
    assert lot_res.status_code == 201, lot_res.text
    lot_id = lot_res.json()["id"]

    results: list[int] = []
    barrier = threading.Barrier(2)

    def attempt_create_heat(heat_no: str) -> None:
        payload = {
            "heat_no": heat_no,
            "heat_date": "2026-10-21",
            "duration_hours": 3.0,
            "alloy": "ADC12",
            "output_kg": 440.00,
            "dross_kg": 20.00,
            "iron_scrap_kg": 2.00,
            "oil_cost": 1000.00,
            "power_cost": 500.00,
            "labour_cost": 500.00,
            "other_cost": 0.00,
            "inputs": [{"lot_id": lot_id, "kg": 500.00}],
        }
        barrier.wait()
        res = auth_client.post("/api/heats", json=payload)
        results.append(res.status_code)

    t1 = threading.Thread(target=attempt_create_heat, args=("H-RACE-001",))
    t2 = threading.Thread(target=attempt_create_heat, args=("H-RACE-002",))

    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert len(results) == 2
    assert sorted(results) == [201, 422], f"Expected exactly one 201 and one 422, got: {results}"

    # Check remaining stock in database
    with postgres_session_factory() as session:
        lot = session.get(PurchaseLot, lot_id)
        assert lot is not None
        inputs = session.scalars(
            select(HeatInput).where(HeatInput.lot_id == lot_id)
        ).all()
        total_consumed = sum(item.kg for item in inputs)
        remaining = lot.weight_kg - total_consumed
        assert total_consumed == Decimal("500.00")
        assert remaining == Decimal("0.00"), f"Remaining stock must be 0.00, got: {remaining}"


def test_concurrent_heat_creation_race_service_level(
    postgres_session_factory: sessionmaker[Session],
) -> None:
    """Direct service-level concurrency test with separate DB sessions and connections.

    Validates that FOR UPDATE serializes the concurrent transactions on PostgreSQL.
    """
    with postgres_session_factory() as session:
        lot = PurchaseLot(
            purchase_date="2026-10-20",
            supplier="Direct Scrap",
            weight_kg=Decimal("500.00"),
            rate_per_kg=Decimal("200.00"),
            gst_mode="WITH",
            transport_mode="SUPPLIER_DELIVERS",
            transport_cost=Decimal("0.00"),
        )
        session.add(lot)
        session.commit()
        lot_id = lot.id

    success_count = 0
    failure_count = 0
    errors: list[Exception] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker(heat_no: str) -> None:
        nonlocal success_count, failure_count
        with postgres_session_factory() as session:
            service = HeatService(session)
            payload = HeatWrite(
                heat_no=heat_no,
                heat_date="2026-10-21",
                duration_hours=Decimal("3.0"),
                alloy="ADC12",
                output_kg=Decimal("440.00"),
                dross_kg=Decimal("20.00"),
                iron_scrap_kg=Decimal("2.00"),
                oil_cost=Decimal("1000.00"),
                power_cost=Decimal("500.00"),
                labour_cost=Decimal("500.00"),
                other_cost=Decimal("0.00"),
                inputs=[HeatInputPayload(lot_id=lot_id, kg=Decimal("500.00"))],
            )
            barrier.wait()
            try:
                service.create(payload)
                with lock:
                    success_count += 1
            except HeatStockError as err:
                with lock:
                    failure_count += 1
                    errors.append(err)

    t1 = threading.Thread(target=worker, args=("H-SRV-001",))
    t2 = threading.Thread(target=worker, args=("H-SRV-002",))

    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert success_count == 1, f"Expected exactly 1 success, got {success_count}"
    assert failure_count == 1, f"Expected exactly 1 failure, got {failure_count}"
    assert len(errors) == 1
    assert "not enough stock" in str(errors[0]).lower()

    with postgres_session_factory() as session:
        lot = session.get(PurchaseLot, lot_id)
        assert lot is not None
        inputs = session.scalars(select(HeatInput).where(HeatInput.lot_id == lot_id)).all()
        total_consumed = sum(item.kg for item in inputs)
        assert total_consumed == Decimal("500.00")
        assert lot.weight_kg - total_consumed == Decimal("0.00")


def test_concurrent_sales_alloy_cap_race(
    auth_client: TestClient,
    postgres_session_factory: sessionmaker[Session],
) -> None:
    """Two concurrent sales race to claim the remaining 500 kg alloy capacity.

    With row locking in PostgreSQL:
    - Exactly one create succeeds (201).
    - Exactly one create fails (422: alloy cap exceeded).
    - Total sold alloy kg ends at 500.00, never exceeding heat output_kg.
    """
    # 1. Create lot and heat with output_kg = 500.00
    lot_res = auth_client.post(
        "/api/purchases",
        json={
            "purchase_date": "2026-10-22",
            "supplier": "Cap Scrap",
            "weight_kg": 600.00,
            "rate_per_kg": 200.00,
            "gst_mode": "WITH",
            "transport_mode": "SUPPLIER_DELIVERS",
            "transport_cost": 0.00,
        },
    )
    lot_id = lot_res.json()["id"]

    heat_res = auth_client.post(
        "/api/heats",
        json={
            "heat_no": "H-CAP-RACE",
            "heat_date": "2026-10-23",
            "duration_hours": 3.5,
            "alloy": "ADC12",
            "output_kg": 500.00,
            "dross_kg": 20.00,
            "iron_scrap_kg": 2.00,
            "oil_cost": 1000.00,
            "power_cost": 500.00,
            "labour_cost": 500.00,
            "other_cost": 0.00,
            "inputs": [{"lot_id": lot_id, "kg": 550.00}],
        },
    )
    heat_id = heat_res.json()["id"]

    results: list[int] = []
    barrier = threading.Barrier(2)

    def attempt_create_sale(customer_name: str) -> None:
        payload = {
            "sale_date": "2026-10-24",
            "customer": customer_name,
            "item_type": "ADC12",
            "heat_id": heat_id,
            "weight_kg": 500.00,
            "rate_per_kg": 250.00,
            "gst_mode": "WITH",
            "transport_mode": "CUSTOMER_ARRANGES",
            "transport_cost": 0.00,
            "transport_billed": 0.00,
        }
        barrier.wait()
        res = auth_client.post("/api/sales", json=payload)
        results.append(res.status_code)

    t1 = threading.Thread(target=attempt_create_sale, args=("Customer 1",))
    t2 = threading.Thread(target=attempt_create_sale, args=("Customer 2",))

    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert len(results) == 2
    assert sorted(results) == [201, 422], f"Expected [201, 422], got: {results}"

    # Verify sold alloy kg in DB is exactly 500.00, never 1000.00
    with postgres_session_factory() as session:
        sales = session.scalars(
            select(Sale).where(Sale.heat_id == heat_id, Sale.item_type == "ADC12")
        ).all()
        total_sold = sum(sale.weight_kg for sale in sales)
        assert total_sold == Decimal("500.00"), f"Total sold must be 500.00, got: {total_sold}"

