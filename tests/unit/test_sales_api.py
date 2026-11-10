from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session, make_engine
from app.main import app
from app.models import Base, Setting

D = Decimal


def lot_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "purchase_date": "2026-10-01",
        "supplier": "Demo Scrap Traders",
        "notes": "Fictional test lot",
        "weight_kg": "1000.00",
        "rate_per_kg": "200.00",
        "gst_mode": "WITH",
        "transport_mode": "WE_PAY",
        "transport_cost": "2000.00",
    }
    payload.update(overrides)
    return payload


def heat_payload(
    *,
    heat_no: str = "H-1001",
    lot_id: int,
    kg: str = "1000.00",
    output_kg: str = "890.00",
    alloy: str = "ADC12",
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "heat_no": heat_no,
        "heat_date": "2026-10-15",
        "duration_hours": "5.50",
        "notes": "Fictional test heat",
        "alloy": alloy,
        "output_kg": output_kg,
        "dross_kg": "60.00",
        "iron_scrap_kg": "5.00",
        "oil_cost": "6000.00",
        "power_cost": "3000.00",
        "labour_cost": "2000.00",
        "other_cost": "0.00",
        "inputs": [{"lot_id": lot_id, "kg": kg}],
    }
    payload.update(overrides)
    return payload


def sale_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "sale_date": "2026-10-20",
        "customer": "Demo Castings",
        "item_type": "ADC12",
        "heat_id": None,
        "weight_kg": "600.00",
        "rate_per_kg": "240.00",
        "gst_mode": "WITH",
        "transport_mode": "WE_PAY_ABSORB",
        "transport_cost": "3000.00",
        "transport_billed": "0.00",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = make_engine(f"sqlite:///{(tmp_path / 'sales.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with factory() as session:
        session.add(
            Setting(
                id=1,
                gst_rate=D("0.18"),
                planned_yield_pct=D("89.00"),
            )
        )
        session.commit()
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


def create_lot(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post("/api/purchases", json=lot_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def create_heat(
    client: TestClient,
    *,
    lot_id: int,
    heat_no: str = "H-1001",
    kg: str = "1000.00",
    output_kg: str = "890.00",
    alloy: str = "ADC12",
    **overrides: object,
) -> dict[str, object]:
    response = client.post(
        "/api/heats",
        json=heat_payload(
            heat_no=heat_no,
            lot_id=lot_id,
            kg=kg,
            output_kg=output_kg,
            alloy=alloy,
            **overrides,
        ),
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_sale(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post("/api/sales", json=sale_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_alloy_sale_updates_heat_values(client: TestClient) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])

    before = client.get(f"/api/heats/{heat['id']}").json()
    assert before["sold_alloy_kg"] == "0.00"
    assert before["is_provisional"] is True

    response = client.post(
        "/api/sales", json=sale_payload(heat_id=heat["id"])
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["heat_id"] == heat["id"]
    assert body["revenue"] == "144000.00"
    assert body["gst_amount"] == "25920.00"
    assert body["net_outbound_transport"] == "3000.00"

    updated = client.get(f"/api/heats/{heat['id']}").json()
    assert updated["sold_alloy_kg"] == "600.00"
    assert updated["revenue"] == "144000.00"
    assert updated["net_outbound_transport"] == "3000.00"
    assert updated["heat_profit"] == "-72000.00"
    assert updated["is_provisional"] is True
    assert len(updated["sales"]) == 1


def test_full_alloy_sale_is_not_provisional(client: TestClient) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])

    response = client.post(
        "/api/sales",
        json=sale_payload(heat_id=heat["id"], weight_kg="890.00"),
    )

    assert response.status_code == 201, response.text
    updated = client.get(f"/api/heats/{heat['id']}").json()
    assert updated["sold_alloy_kg"] == "890.00"
    assert updated["is_provisional"] is False


def test_worked_example_profit_includes_linked_byproducts(
    client: TestClient,
) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])

    alloy = client.post(
        "/api/sales",
        json=sale_payload(heat_id=heat["id"], weight_kg="890.00"),
    )
    assert alloy.status_code == 201, alloy.text
    alloy_sale_id = alloy.json()["id"]
    assert (
        client.post(
            "/api/sales",
            json=sale_payload(
                item_type="DROSS",
                heat_id=heat["id"],
                weight_kg="60.00",
                rate_per_kg="90.00",
                transport_mode="CUSTOMER_ARRANGES",
                transport_cost="0.00",
            ),
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/sales",
            json=sale_payload(
                item_type="IRON_SCRAP",
                heat_id=heat["id"],
                weight_kg="5.00",
                rate_per_kg="32.00",
                gst_mode="WITHOUT",
                transport_mode="CUSTOMER_ARRANGES",
                transport_cost="0.00",
            ),
        ).status_code
        == 201
    )

    updated = client.get(f"/api/heats/{heat['id']}").json()
    assert updated["revenue"] == "219160.00"
    assert updated["net_outbound_transport"] == "3000.00"
    assert updated["heat_profit"] == "3160.00"
    assert updated["sold_alloy_kg"] == "890.00"
    assert updated["is_provisional"] is False
    assert [sale["item_type"] for sale in updated["sales"]] == [
        "ADC12",
        "DROSS",
        "IRON_SCRAP",
    ]

    billed = client.put(
        f"/api/sales/{alloy_sale_id}",
        json=sale_payload(
            heat_id=heat["id"],
            weight_kg="890.00",
            transport_mode="WE_PAY_BILL",
            transport_cost="3000.00",
            transport_billed="2000.00",
        ),
    )
    assert billed.status_code == 200, billed.text
    assert billed.json()["net_outbound_transport"] == "1000.00"

    after_billing = client.get(f"/api/heats/{heat['id']}").json()
    assert after_billing["revenue"] == "219160.00"
    assert after_billing["net_outbound_transport"] == "1000.00"
    assert after_billing["heat_profit"] == "5160.00"


def test_dross_and_iron_sales_may_be_unlinked(client: TestClient) -> None:
    dross = client.post(
        "/api/sales",
        json=sale_payload(
            item_type="DROSS",
            heat_id=None,
            weight_kg="60.00",
            rate_per_kg="90.00",
            transport_mode="CUSTOMER_ARRANGES",
            transport_cost="0.00",
        ),
    )
    iron = client.post(
        "/api/sales",
        json=sale_payload(
            item_type="IRON_SCRAP",
            heat_id=None,
            weight_kg="5.00",
            rate_per_kg="32.00",
            transport_mode="CUSTOMER_ARRANGES",
            transport_cost="0.00",
        ),
    )

    assert dross.status_code == 201, dross.text
    assert iron.status_code == 201, iron.text
    assert dross.json()["heat_id"] is None
    assert iron.json()["heat_id"] is None


@pytest.mark.parametrize("item_type", ["ADC12", "LM6"])
def test_alloy_sale_requires_matching_heat(
    client: TestClient, item_type: str
) -> None:
    other_alloy = "LM6" if item_type == "ADC12" else "ADC12"
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"], alloy=other_alloy)

    missing = client.post(
        "/api/sales", json=sale_payload(item_type=item_type, heat_id=None)
    )
    assert missing.status_code == 422, missing.text

    wrong = client.post(
        "/api/sales",
        json=sale_payload(
            item_type=item_type,
            heat_id=heat["id"],
        ),
    )
    assert wrong.status_code == 422, wrong.text
    assert client.get("/api/sales").json() == []


def test_alloy_sales_cannot_exceed_heat_output(client: TestClient) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])

    first = client.post(
        "/api/sales",
        json=sale_payload(heat_id=heat["id"], weight_kg="800.00"),
    )
    assert first.status_code == 201, first.text

    too_much = client.post(
        "/api/sales",
        json=sale_payload(heat_id=heat["id"], weight_kg="91.00"),
    )
    assert too_much.status_code == 422, too_much.text

    exact = client.post(
        "/api/sales",
        json=sale_payload(heat_id=heat["id"], weight_kg="90.00"),
    )
    assert exact.status_code == 201, exact.text

    updated = client.get(f"/api/heats/{heat['id']}").json()
    assert updated["sold_alloy_kg"] == "890.00"
    assert updated["is_provisional"] is False


def test_update_sale_excludes_its_own_alloy_kg(client: TestClient) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])
    sale = create_sale(client, heat_id=heat["id"], weight_kg="600.00")

    exact = client.put(
        f"/api/sales/{sale['id']}",
        json=sale_payload(heat_id=heat["id"], weight_kg="890.00"),
    )
    assert exact.status_code == 200, exact.text

    too_much = client.put(
        f"/api/sales/{sale['id']}",
        json=sale_payload(heat_id=heat["id"], weight_kg="900.00"),
    )
    assert too_much.status_code == 422, too_much.text
    assert (
        client.get(f"/api/sales/{sale['id']}").json()["weight_kg"]
        == "890.00"
    )


@pytest.mark.parametrize(
    ("mode", "cost", "billed", "expected_cost", "expected_billed", "net"),
    [
        ("CUSTOMER_ARRANGES", "500.00", "300.00", "0.00", "0.00", "0.00"),
        ("WE_PAY_ABSORB", "3000.00", "2000.00", "3000.00", "0.00", "3000.00"),
        ("WE_PAY_BILL", "3000.00", "2000.00", "3000.00", "2000.00", "1000.00"),
        ("WE_PAY_BILL", "3000.00", "3000.00", "3000.00", "3000.00", "0.00"),
    ],
)
def test_transport_modes_are_normalised_and_computed(
    client: TestClient,
    mode: str,
    cost: str,
    billed: str,
    expected_cost: str,
    expected_billed: str,
    net: str,
) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])

    response = client.post(
        "/api/sales",
        json=sale_payload(
            heat_id=heat["id"],
            transport_mode=mode,
            transport_cost=cost,
            transport_billed=billed,
        ),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["transport_cost"] == expected_cost
    assert body["transport_billed"] == expected_billed
    assert body["net_outbound_transport"] == net


def test_we_pay_bill_rejects_billed_above_cost(client: TestClient) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])

    response = client.post(
        "/api/sales",
        json=sale_payload(
            heat_id=heat["id"],
            transport_mode="WE_PAY_BILL",
            transport_cost="3000.00",
            transport_billed="3000.01",
        ),
    )

    assert response.status_code == 422, response.text
    assert client.get("/api/sales").json() == []


def test_gst_mode_never_changes_heat_profit(client: TestClient) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])
    sale = create_sale(client, heat_id=heat["id"], weight_kg="600.00")

    with_gst = client.get(f"/api/heats/{heat['id']}").json()
    assert with_gst["heat_profit"] == "-72000.00"
    assert (
        client.get(f"/api/sales/{sale['id']}").json()["gst_amount"]
        == "25920.00"
    )

    updated = client.put(
        f"/api/sales/{sale['id']}",
        json=sale_payload(
            heat_id=heat["id"],
            weight_kg="600.00",
            gst_mode="WITHOUT",
        ),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["gst_amount"] == "0.00"

    without_gst = client.get(f"/api/heats/{heat['id']}").json()
    assert without_gst["heat_profit"] == with_gst["heat_profit"]


def test_delete_sale_releases_alloy_capacity(client: TestClient) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])
    sale = create_sale(client, heat_id=heat["id"], weight_kg="890.00")

    deleted = client.delete(f"/api/sales/{sale['id']}")
    assert deleted.status_code == 204
    assert deleted.content == b""

    updated = client.get(f"/api/heats/{heat['id']}").json()
    assert updated["sold_alloy_kg"] == "0.00"
    assert updated["is_provisional"] is True

    replacement = client.post(
        "/api/sales",
        json=sale_payload(heat_id=heat["id"], weight_kg="890.00"),
    )
    assert replacement.status_code == 201, replacement.text


def test_update_sale_can_move_to_another_matching_heat(
    client: TestClient,
) -> None:
    first_lot = create_lot(client)
    second_lot = create_lot(
        client, supplier="Second Demo Lot", purchase_date="2026-09-01"
    )
    first = create_heat(client, lot_id=first_lot["id"], heat_no="H-1")
    second = create_heat(client, lot_id=second_lot["id"], heat_no="H-2")
    sale = create_sale(client, heat_id=first["id"], weight_kg="600.00")

    moved = client.put(
        f"/api/sales/{sale['id']}",
        json=sale_payload(heat_id=second["id"], weight_kg="600.00"),
    )

    assert moved.status_code == 200, moved.text
    assert client.get(f"/api/heats/{first['id']}").json()["sold_alloy_kg"] == (
        "0.00"
    )
    assert client.get(f"/api/heats/{second['id']}").json()["sold_alloy_kg"] == (
        "600.00"
    )


def test_heat_with_sales_cannot_be_deleted(client: TestClient) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])
    sale = create_sale(client, heat_id=heat["id"])

    response = client.delete(f"/api/heats/{heat['id']}")

    assert response.status_code == 409, response.text
    remaining = client.get(f"/api/heats/{heat['id']}").json()
    assert len(remaining["inputs"]) == 1
    assert len(remaining["sales"]) == 1
    assert client.get(f"/api/sales/{sale['id']}").status_code == 200


def test_reducing_heat_output_below_sold_alloy_is_rejected(
    client: TestClient,
) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])
    create_sale(client, heat_id=heat["id"], weight_kg="600.00")

    too_small = client.put(
        f"/api/heats/{heat['id']}",
        json=heat_payload(
            heat_no=heat["heat_no"],
            lot_id=lot["id"],
            output_kg="599.00",
        ),
    )
    assert too_small.status_code == 422, too_small.text
    assert (
        client.get(f"/api/heats/{heat['id']}").json()["output_kg"]
        == "890.00"
    )

    exact = client.put(
        f"/api/heats/{heat['id']}",
        json=heat_payload(
            heat_no=heat["heat_no"],
            lot_id=lot["id"],
            output_kg="600.00",
        ),
    )
    assert exact.status_code == 200, exact.text
    assert exact.json()["is_provisional"] is False


def test_unknown_sale_returns_404(client: TestClient) -> None:
    assert client.get("/api/sales/999999").status_code == 404
    assert (
        client.put("/api/sales/999999", json=sale_payload()).status_code
        == 404
    )
    assert client.delete("/api/sales/999999").status_code == 404


def test_unknown_heat_in_sale_payload_returns_422(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/sales", json=sale_payload(heat_id=999999)
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "field",
    ["weight_kg", "rate_per_kg", "transport_cost", "transport_billed"],
)
def test_sale_numbers_require_two_decimals(
    client: TestClient, field: str
) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])
    overrides: dict[str, object] = {"heat_id": heat["id"], field: "1.234"}
    if field == "transport_billed":
        overrides["transport_mode"] = "WE_PAY_BILL"
        overrides["transport_cost"] = "2.00"

    response = client.post("/api/sales", json=sale_payload(**overrides))

    assert response.status_code == 422, response.text
    assert client.get("/api/sales").json() == []


def test_sale_requires_a_customer(client: TestClient) -> None:
    lot = create_lot(client)
    heat = create_heat(client, lot_id=lot["id"])

    response = client.post(
        "/api/sales", json=sale_payload(heat_id=heat["id"], customer="  ")
    )

    assert response.status_code == 422, response.text
    assert client.get("/api/sales").json() == []
