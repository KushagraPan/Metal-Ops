"""PostgreSQL parity, Alembic migrations, and schema constraint tests.

Acceptance criteria:
- The full Alembic chain runs from empty on Postgres; seed runs twice with identical row counts.
- Behaviour that differs between SQLite and Postgres (Decimal precision, case-insensitive heat
  search, constraint errors, 409/422 mapping) is covered.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Heat,
    HeatInput,
    PurchaseLot,
    Sale,
    Setting,
    SpectroReport,
)
from app.seed import seed
from app.storage import LocalStorage


pytestmark = pytest.mark.integration


def test_alembic_chain_and_idempotent_seed(
    postgres_engine,
    tmp_path: Path,
) -> None:
    """Run full Alembic migration chain from empty on PostgreSQL, then run seed twice."""
    # 1. Wipe schema to completely empty
    with postgres_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO metalops_test;"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))

    # 2. Run Alembic upgrade head
    repo_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(repo_root / "alembic.ini")
    alembic_cfg.set_main_option(
        "sqlalchemy.url", postgres_engine.url.render_as_string(hide_password=False)
    )
    alembic_cfg.set_main_option("script_location", str(repo_root / "migrations"))

    command.upgrade(alembic_cfg, "head")

    # Verify tables created
    with postgres_engine.connect() as conn:
        tables_res = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"
            )
        ).fetchall()
        tables = {row[0] for row in tables_res}
        assert "purchase_lots" in tables
        assert "heats" in tables
        assert "heat_inputs" in tables
        assert "sales" in tables
        assert "spectro_reports" in tables
        assert "settings" in tables
        assert "alembic_version" in tables

    # 3. Seed first time
    storage = LocalStorage(tmp_path / "seed_storage")
    session_factory = sessionmaker(bind=postgres_engine, class_=Session, expire_on_commit=False)
    with session_factory() as session:
        first_counts = seed(session, storage=storage)

    assert first_counts["lots"] >= 3
    assert first_counts["heats"] >= 3
    assert first_counts["sales"] >= 5
    assert first_counts["reports"] >= 1
    assert first_counts["settings"] == 1

    # 4. Seed second time (idempotence)
    with session_factory() as session:
        second_counts = seed(session, storage=storage)

    assert second_counts == first_counts

    # Verify database counts directly
    with session_factory() as session:
        lots_count = session.scalar(select(func.count(PurchaseLot.id)))
        heats_count = session.scalar(select(func.count(Heat.id)))
        sales_count = session.scalar(select(func.count(Sale.id)))
        reports_count = session.scalar(select(func.count(SpectroReport.id)))

        assert lots_count == first_counts["lots"]
        assert heats_count == first_counts["heats"]
        assert sales_count == first_counts["sales"]
        assert reports_count == first_counts["reports"]


def test_postgres_decimal_precision(auth_client: TestClient) -> None:
    """Verify Decimal precision (2 decimal places) on PostgreSQL without float drift."""
    lot_payload = {
        "purchase_date": "2026-10-01",
        "supplier": "Precision Metals",
        "weight_kg": 1234.56,
        "rate_per_kg": 234.56,
        "gst_mode": "WITH",
        "transport_mode": "WE_PAY",
        "transport_cost": 789.12,
    }
    res = auth_client.post("/api/purchases", json=lot_payload)
    assert res.status_code == 201, res.text
    data = res.json()

    assert Decimal(str(data["weight_kg"])) == Decimal("1234.56")
    assert Decimal(str(data["rate_per_kg"])) == Decimal("234.56")
    assert Decimal(str(data["transport_cost"])) == Decimal("789.12")
    # Base: 1234.56 * 234.56 = 289578.3936 + 789.12 = 290367.5136 / 1234.56 = 235.19919... -> 235.20
    assert Decimal(str(data["landed_cost_per_kg"])) == Decimal("235.20")
    # GST: 1234.56 * 234.56 * 0.18 = 52124.110848 -> 52124.11
    assert Decimal(str(data["gst_amount"])) == Decimal("52124.11")


def test_postgres_case_insensitive_heat_search(auth_client: TestClient) -> None:
    """Verify PostgreSQL ILIKE case-insensitivity on heat_no searches."""
    # 1. Create a lot
    lot_res = auth_client.post(
        "/api/purchases",
        json={
            "purchase_date": "2026-10-02",
            "supplier": "Search Scrap",
            "weight_kg": 1000.00,
            "rate_per_kg": 200.00,
            "gst_mode": "WITHOUT",
            "transport_mode": "SUPPLIER_DELIVERS",
            "transport_cost": 0.00,
        },
    )
    lot_id = lot_res.json()["id"]

    # 2. Create heats with mixed case heat_no
    for heat_no in ["H-ALPHA-01", "H-Beta-02", "h-gamma-03"]:
        auth_client.post(
            "/api/heats",
            json={
                "heat_no": heat_no,
                "heat_date": "2026-10-05",
                "duration_hours": 3.0,
                "alloy": "ADC12",
                "output_kg": 200.00,
                "dross_kg": 10.00,
                "iron_scrap_kg": 1.00,
                "oil_cost": 0.00,
                "power_cost": 0.00,
                "labour_cost": 0.00,
                "other_cost": 0.00,
                "inputs": [{"lot_id": lot_id, "kg": 250.00}],
            },
        )

    # Search with lower case for uppercase heat_no
    res_lower = auth_client.get("/api/heats?heat_no=alpha")
    assert res_lower.status_code == 200
    assert any(h["heat_no"] == "H-ALPHA-01" for h in res_lower.json())

    # Search with upper case for lowercase heat_no
    res_upper = auth_client.get("/api/heats?heat_no=GAMMA")
    assert res_upper.status_code == 200
    assert any(h["heat_no"] == "h-gamma-03" for h in res_upper.json())

    # Search with mixed case
    res_mixed = auth_client.get("/api/heats?heat_no=bEtA")
    assert res_mixed.status_code == 200
    assert any(h["heat_no"] == "H-Beta-02" for h in res_mixed.json())


def test_postgres_constraint_errors_and_conflict_mapping(auth_client: TestClient) -> None:
    """Verify database unique constraint violations and FK in-use map to 409 / 422."""
    # 1. Create a lot and heat
    lot_res = auth_client.post(
        "/api/purchases",
        json={
            "purchase_date": "2026-10-03",
            "supplier": "Constraint Test",
            "weight_kg": 500.00,
            "rate_per_kg": 200.00,
            "gst_mode": "WITHOUT",
            "transport_mode": "SUPPLIER_DELIVERS",
            "transport_cost": 0.00,
        },
    )
    lot_id = lot_res.json()["id"]

    heat_payload = {
        "heat_no": "H-UNIQUE-01",
        "heat_date": "2026-10-05",
        "duration_hours": 3.0,
        "alloy": "ADC12",
        "output_kg": 400.00,
        "dross_kg": 20.00,
        "iron_scrap_kg": 2.00,
        "oil_cost": 0.00,
        "power_cost": 0.00,
        "labour_cost": 0.00,
        "other_cost": 0.00,
        "inputs": [{"lot_id": lot_id, "kg": 450.00}],
    }
    h1 = auth_client.post("/api/heats", json=heat_payload)
    assert h1.status_code == 201
    heat_id = h1.json()["id"]

    # 2. Duplicate heat_no -> 409 Conflict
    dup_res = auth_client.post("/api/heats", json=heat_payload)
    assert dup_res.status_code == 409, f"Duplicate heat_no should return 409, got {dup_res.status_code}"

    # 3. Add a sale referencing this heat
    sale_res = auth_client.post(
        "/api/sales",
        json={
            "sale_date": "2026-10-06",
            "customer": "Test Customer",
            "item_type": "ADC12",
            "heat_id": heat_id,
            "weight_kg": 200.00,
            "rate_per_kg": 240.00,
            "gst_mode": "WITH",
            "transport_mode": "CUSTOMER_ARRANGES",
            "transport_cost": 0.00,
            "transport_billed": 0.00,
        },
    )
    assert sale_res.status_code == 201

    # 4. Deleting heat with linked sale -> 409 Conflict
    del_res = auth_client.delete(f"/api/heats/{heat_id}")
    assert del_res.status_code == 409, f"Deleting heat with linked sale should return 409, got {del_res.status_code}"

    # 5. Invalid input reference (unknown lot_id) -> 422 Unprocessable Entity
    bad_heat = auth_client.post(
        "/api/heats",
        json={
            "heat_no": "H-BAD-INPUT",
            "heat_date": "2026-10-05",
            "duration_hours": 3.0,
            "alloy": "ADC12",
            "output_kg": 100.00,
            "dross_kg": 5.00,
            "iron_scrap_kg": 1.00,
            "oil_cost": 0.00,
            "power_cost": 0.00,
            "labour_cost": 0.00,
            "other_cost": 0.00,
            "inputs": [{"lot_id": 999999, "kg": 100.00}],
        },
    )
    assert bad_heat.status_code == 422
