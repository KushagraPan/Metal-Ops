from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path
import threading

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


def heat_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "heat_no": "H-1001",
        "heat_date": "2026-10-15",
        "duration_hours": "5.50",
        "notes": "Fictional test heat",
        "alloy": "ADC12",
        "output_kg": "890.00",
        "dross_kg": "60.00",
        "iron_scrap_kg": "5.00",
        "oil_cost": "6000.00",
        "power_cost": "3000.00",
        "labour_cost": "2000.00",
        "other_cost": "0.00",
        "inputs": [],
    }
    payload.update(overrides)
    return payload


def input_payload(lot_id: int, kg: str) -> dict[str, object]:
    return {"lot_id": lot_id, "kg": kg}


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = make_engine(f"sqlite:///{(tmp_path / 'heats.db').as_posix()}")
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


def test_create_heat_returns_computed_values(client: TestClient) -> None:
    lot = create_lot(client)

    response = client.post(
        "/api/heats",
        json=heat_payload(
            inputs=[input_payload(lot["id"], "1000.00")],
        ),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["heat_no"] == "H-1001"
    assert body["alloy"] == "ADC12"
    assert body["inputs"] == [
        {
            "lot_id": lot["id"],
            "kg": "1000.00",
            "supplier": "Demo Scrap Traders",
            "purchase_date": "2026-10-01",
            "landed_cost_per_kg": "202.00",
        }
    ]
    assert body["total_input_kg"] == "1000.00"
    assert body["yield_pct"] == "89.00"
    assert body["scrap_cost"] == "202000.00"
    assert body["variable_costs"] == "11000.00"
    assert body["heat_profit"] == "-213000.00"

    purchase = client.get(f"/api/purchases/{lot['id']}").json()
    assert purchase["consumed_kg"] == "1000.00"
    assert purchase["remaining_kg"] == "0.00"


def test_empty_inputs_are_valid_with_null_yield_and_profit(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/heats",
        json=heat_payload(output_kg="100.00", inputs=[]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["inputs"] == []
    assert body["total_input_kg"] == "0.00"
    assert body["yield_pct"] is None
    assert body["scrap_cost"] == "0.00"
    assert body["heat_profit"] is None

    fetched = client.get(f"/api/heats/{body['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["yield_pct"] is None
    assert fetched.json()["heat_profit"] is None


def test_over_consumption_returns_422_and_saves_nothing(
    client: TestClient,
) -> None:
    lot = create_lot(client)

    response = client.post(
        "/api/heats",
        json=heat_payload(
            inputs=[input_payload(lot["id"], "1000.01")],
        ),
    )

    assert response.status_code == 422, response.text
    assert client.get("/api/heats").json() == []
    purchase = client.get(f"/api/purchases/{lot['id']}").json()
    assert purchase["remaining_kg"] == "1000.00"


def test_duplicate_inputs_for_same_lot_are_merged(
    client: TestClient,
) -> None:
    lot = create_lot(client)

    response = client.post(
        "/api/heats",
        json=heat_payload(
            inputs=[
                input_payload(lot["id"], "400.00"),
                input_payload(lot["id"], "600.00"),
            ],
        ),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["inputs"]) == 1
    assert body["inputs"][0]["kg"] == "1000.00"
    assert body["total_input_kg"] == "1000.00"
    purchase = client.get(f"/api/purchases/{lot['id']}").json()
    assert purchase["remaining_kg"] == "0.00"


def test_duplicate_inputs_are_summed_before_stock_check(
    client: TestClient,
) -> None:
    lot = create_lot(client)

    response = client.post(
        "/api/heats",
        json=heat_payload(
            inputs=[
                input_payload(lot["id"], "600.00"),
                input_payload(lot["id"], "600.00"),
            ],
        ),
    )

    assert response.status_code == 422, response.text
    assert client.get("/api/heats").json() == []
    purchase = client.get(f"/api/purchases/{lot['id']}").json()
    assert purchase["remaining_kg"] == "1000.00"


def test_multi_input_failure_saves_neither_heat_nor_inputs(
    client: TestClient,
) -> None:
    lot_a = create_lot(client)
    lot_b = create_lot(
        client,
        purchase_date="2026-09-01",
        supplier="Second Demo Lot",
        weight_kg="50.00",
    )

    response = client.post(
        "/api/heats",
        json=heat_payload(
            inputs=[
                input_payload(lot_a["id"], "1000.00"),
                input_payload(lot_b["id"], "50.01"),
            ],
        ),
    )

    assert response.status_code == 422, response.text
    assert client.get("/api/heats").json() == []
    assert (
        client.get(f"/api/purchases/{lot_a['id']}").json()["remaining_kg"]
        == "1000.00"
    )
    assert (
        client.get(f"/api/purchases/{lot_b['id']}").json()["remaining_kg"]
        == "50.00"
    )


def test_unknown_lot_id_returns_422_and_saves_nothing(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/heats",
        json=heat_payload(inputs=[input_payload(999999, "1.00")]),
    )

    assert response.status_code == 422, response.text
    assert client.get("/api/heats").json() == []


def test_duplicate_heat_no_returns_409(client: TestClient) -> None:
    first = client.post("/api/heats", json=heat_payload())
    assert first.status_code == 201, first.text

    second = client.post("/api/heats", json=heat_payload())

    assert second.status_code == 409, second.text
    assert len(client.get("/api/heats").json()) == 1


def test_get_update_and_delete_heat(client: TestClient) -> None:
    lot = create_lot(client)
    created = client.post(
        "/api/heats",
        json=heat_payload(inputs=[input_payload(lot["id"], "1000.00")]),
    ).json()
    heat_id = created["id"]

    fetched = client.get(f"/api/heats/{heat_id}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["heat_no"] == "H-1001"

    updated = client.put(
        f"/api/heats/{heat_id}",
        json=heat_payload(
            heat_no="H-1002",
            output_kg="900.00",
            dross_kg="70.00",
            inputs=[input_payload(lot["id"], "1000.00")],
        ),
    )

    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["heat_no"] == "H-1002"
    assert body["output_kg"] == "900.00"
    assert body["yield_pct"] == "90.00"

    deleted = client.delete(f"/api/heats/{heat_id}")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/api/heats/{heat_id}").status_code == 404


def test_update_excludes_the_heats_own_consumption(
    client: TestClient,
) -> None:
    lot = create_lot(client, weight_kg="100.00")
    first = client.post(
        "/api/heats",
        json=heat_payload(
            heat_no="H-1",
            output_kg="80.00",
            inputs=[input_payload(lot["id"], "80.00")],
        ),
    ).json()
    second = client.post(
        "/api/heats",
        json=heat_payload(
            heat_no="H-2",
            output_kg="20.00",
            inputs=[input_payload(lot["id"], "20.00")],
        ),
    )
    assert second.status_code == 201, second.text

    same = client.put(
        f"/api/heats/{first['id']}",
        json=heat_payload(
            heat_no="H-1",
            output_kg="80.00",
            inputs=[input_payload(lot["id"], "80.00")],
        ),
    )
    assert same.status_code == 200, same.text

    too_much = client.put(
        f"/api/heats/{first['id']}",
        json=heat_payload(
            heat_no="H-1",
            output_kg="81.00",
            inputs=[input_payload(lot["id"], "81.00")],
        ),
    )
    assert too_much.status_code == 422, too_much.text
    purchase = client.get(f"/api/purchases/{lot['id']}").json()
    assert purchase["remaining_kg"] == "0.00"


def test_update_switching_lots_releases_the_old_lot(
    client: TestClient,
) -> None:
    old_lot = create_lot(client)
    new_lot = create_lot(
        client,
        purchase_date="2026-09-01",
        supplier="Replacement Demo Lot",
        weight_kg="100.00",
    )
    created = client.post(
        "/api/heats",
        json=heat_payload(
            output_kg="60.00",
            inputs=[input_payload(old_lot["id"], "60.00")],
        ),
    ).json()

    response = client.put(
        f"/api/heats/{created['id']}",
        json=heat_payload(
            output_kg="40.00",
            inputs=[input_payload(new_lot["id"], "40.00")],
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["inputs"][0]["lot_id"] == new_lot["id"]
    assert (
        client.get(f"/api/purchases/{old_lot['id']}").json()["remaining_kg"]
        == "1000.00"
    )
    assert (
        client.get(f"/api/purchases/{new_lot['id']}").json()["remaining_kg"]
        == "60.00"
    )


def test_delete_heat_restores_stock_and_clears_purchase_409(
    client: TestClient,
) -> None:
    lot = create_lot(client)
    heat = client.post(
        "/api/heats",
        json=heat_payload(
            output_kg="100.00",
            inputs=[input_payload(lot["id"], "100.00")],
        ),
    ).json()

    assert client.delete(f"/api/purchases/{lot['id']}").status_code == 409

    assert client.delete(f"/api/heats/{heat['id']}").status_code == 204

    purchase = client.get(f"/api/purchases/{lot['id']}").json()
    assert purchase["remaining_kg"] == "1000.00"
    assert client.delete(f"/api/purchases/{lot['id']}").status_code == 204
    assert client.get(f"/api/heats/{heat['id']}").status_code == 404


@pytest.mark.parametrize("kg", ["0", "-1", "1.234"])
def test_input_kg_must_be_positive_with_two_decimals(
    client: TestClient, kg: str
) -> None:
    lot = create_lot(client)

    response = client.post(
        "/api/heats",
        json=heat_payload(inputs=[input_payload(lot["id"], kg)]),
    )

    assert response.status_code == 422, response.text
    assert client.get("/api/heats").json() == []
    assert (
        client.get(f"/api/purchases/{lot['id']}").json()["remaining_kg"]
        == "1000.00"
    )


@pytest.mark.parametrize("output", ["0", "-1", "1.234"])
def test_output_must_be_positive_with_two_decimals(
    client: TestClient, output: str
) -> None:
    response = client.post(
        "/api/heats", json=heat_payload(output_kg=output, inputs=[])
    )

    assert response.status_code == 422, response.text
    assert client.get("/api/heats").json() == []


def test_output_cannot_exceed_total_input(
    client: TestClient,
) -> None:
    lot = create_lot(client, weight_kg="100.00")

    response = client.post(
        "/api/heats",
        json=heat_payload(
            output_kg="100.01",
            inputs=[input_payload(lot["id"], "100.00")],
        ),
    )

    assert response.status_code == 422, response.text
    assert client.get("/api/heats").json() == []
    assert (
        client.get(f"/api/purchases/{lot['id']}").json()["remaining_kg"]
        == "100.00"
    )


def test_output_equal_to_total_input_is_allowed(
    client: TestClient,
) -> None:
    lot = create_lot(client, weight_kg="100.00")

    response = client.post(
        "/api/heats",
        json=heat_payload(
            output_kg="100.00",
            inputs=[input_payload(lot["id"], "100.00")],
        ),
    )

    assert response.status_code == 201, response.text
    assert response.json()["yield_pct"] == "100.00"


@pytest.mark.parametrize(
    "field",
    [
        "dross_kg",
        "iron_scrap_kg",
        "oil_cost",
        "power_cost",
        "labour_cost",
        "other_cost",
    ],
)
def test_heat_weights_and_costs_require_two_decimals(
    client: TestClient, field: str
) -> None:
    response = client.post(
        "/api/heats", json=heat_payload(**{field: "1.234"})
    )

    assert response.status_code == 422, response.text
    assert client.get("/api/heats").json() == []


def test_unknown_heat_returns_404(client: TestClient) -> None:
    assert client.get("/api/heats/999999").status_code == 404
    assert (
        client.put("/api/heats/999999", json=heat_payload()).status_code
        == 404
    )
    assert client.delete("/api/heats/999999").status_code == 404


def test_update_rejects_duplicate_heat_no(client: TestClient) -> None:
    first = client.post(
        "/api/heats", json=heat_payload(heat_no="H-1001")
    ).json()
    second = client.post(
        "/api/heats", json=heat_payload(heat_no="H-1002")
    ).json()

    response = client.put(
        f"/api/heats/{second['id']}",
        json=heat_payload(heat_no="H-1001"),
    )

    assert response.status_code == 409, response.text
    assert client.get(f"/api/heats/{second['id']}").json()["heat_no"] == (
        "H-1002"
    )


def test_concurrent_creates_cannot_overconsume_a_lot(
    client: TestClient,
) -> None:
    lot = create_lot(client, weight_kg="100.00")
    barrier = threading.Barrier(2)

    def attempt(index: int):
        barrier.wait(timeout=5)
        return client.post(
            "/api/heats",
            json=heat_payload(
                heat_no=f"H-RACE-{index}",
                output_kg="100.00",
                inputs=[input_payload(lot["id"], "100.00")],
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [
            future.result()
            for future in [pool.submit(attempt, 1), pool.submit(attempt, 2)]
        ]

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201, 422], [response.text for response in responses]
    assert len(client.get("/api/heats").json()) == 1
    purchase = client.get(f"/api/purchases/{lot['id']}").json()
    assert purchase["remaining_kg"] == "0.00"
