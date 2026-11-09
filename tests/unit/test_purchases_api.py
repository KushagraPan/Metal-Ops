from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session, make_engine
from app.main import app
from app.models import Alloy, Base, Heat, HeatInput, Setting

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


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = make_engine(
        f"sqlite:///{(tmp_path / 'purchases.db').as_posix()}"
    )
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


def consume_lot(
    session_factory: sessionmaker[Session], lot_id: int, kg: Decimal
) -> None:
    with session_factory() as session:
        heat = Heat(
            heat_no=f"H-TEST-{uuid4().hex[:8]}",
            heat_date=date(2026, 10, 15),
            alloy=Alloy.ADC12,
            output_kg=kg,
        )
        session.add(heat)
        session.flush()
        session.add(HeatInput(heat_id=heat.id, lot_id=lot_id, kg=kg))
        session.commit()


def test_create_with_gst_returns_gst_and_landed_cost(
    client: TestClient,
) -> None:
    response = client.post("/api/purchases", json=lot_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["gst_mode"] == "WITH"
    assert body["gst_amount"] == "36000.00"
    assert body["landed_cost_per_kg"] == "202.00"
    assert body["remaining_kg"] == "1000.00"
    assert body["consumed_kg"] == "0.00"
    assert D(body["transport_cost"]) == D("2000.00")


def test_create_without_gst_returns_zero_gst(client: TestClient) -> None:
    response = client.post(
        "/api/purchases", json=lot_payload(gst_mode="WITHOUT")
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["gst_mode"] == "WITHOUT"
    assert body["gst_amount"] == "0.00"
    assert body["landed_cost_per_kg"] == "202.00"


def test_supplier_delivers_forces_transport_cost_to_zero(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/purchases",
        json=lot_payload(
            transport_mode="SUPPLIER_DELIVERS", transport_cost="500.00"
        ),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["transport_mode"] == "SUPPLIER_DELIVERS"
    assert D(body["transport_cost"]) == D("0.00")
    assert body["landed_cost_per_kg"] == "200.00"


@pytest.mark.parametrize(
    "transport_cost", [None, "0", "0.00", "-1"]
)
def test_we_pay_requires_positive_transport_cost(
    client: TestClient, transport_cost: str | None
) -> None:
    payload = lot_payload()
    if transport_cost is None:
        payload.pop("transport_cost")
    else:
        payload["transport_cost"] = transport_cost

    response = client.post("/api/purchases", json=payload)

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("weight_kg", "0"),
        ("weight_kg", "-1"),
        ("rate_per_kg", "0"),
        ("rate_per_kg", "-1"),
    ],
)
def test_weight_and_rate_must_be_positive(
    client: TestClient, field: str, value: str
) -> None:
    response = client.post(
        "/api/purchases", json=lot_payload(**{field: value})
    )

    assert response.status_code == 422, response.text
    assert client.get("/api/purchases").json() == []


def test_list_shows_remaining_kg_after_heat_inputs(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    created = client.post("/api/purchases", json=lot_payload()).json()
    unused = client.post(
        "/api/purchases",
        json=lot_payload(
            purchase_date="2026-09-01", supplier="Unused Demo Lot"
        ),
    ).json()
    consume_lot(session_factory, created["id"], D("250.00"))

    response = client.get("/api/purchases")

    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 2
    by_id = {row["id"]: row for row in rows}
    assert by_id[created["id"]]["consumed_kg"] == "250.00"
    assert by_id[created["id"]]["remaining_kg"] == "750.00"
    assert by_id[created["id"]]["gst_amount"] == "36000.00"
    assert by_id[created["id"]]["landed_cost_per_kg"] == "202.00"
    assert by_id[unused["id"]]["consumed_kg"] == "0.00"
    assert by_id[unused["id"]]["remaining_kg"] == "1000.00"


def test_get_update_and_delete(client: TestClient) -> None:
    created = client.post("/api/purchases", json=lot_payload()).json()
    lot_id = created["id"]

    fetched = client.get(f"/api/purchases/{lot_id}")
    assert fetched.status_code == 200
    assert fetched.json()["supplier"] == "Demo Scrap Traders"

    updated = client.put(
        f"/api/purchases/{lot_id}",
        json=lot_payload(
            supplier="Updated Demo Supplier",
            weight_kg="1200.00",
            rate_per_kg="210.00",
            gst_mode="WITHOUT",
            transport_mode="SUPPLIER_DELIVERS",
            transport_cost="0.00",
        ),
    )

    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["supplier"] == "Updated Demo Supplier"
    assert D(body["weight_kg"]) == D("1200.00")
    assert body["gst_amount"] == "0.00"
    assert body["landed_cost_per_kg"] == "210.00"
    assert body["remaining_kg"] == "1200.00"

    deleted = client.delete(f"/api/purchases/{lot_id}")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/api/purchases/{lot_id}").status_code == 404


def test_unknown_lot_returns_404(client: TestClient) -> None:
    assert client.get("/api/purchases/999").status_code == 404
    assert (
        client.put("/api/purchases/999", json=lot_payload()).status_code
        == 404
    )
    assert client.delete("/api/purchases/999").status_code == 404


def test_update_rejects_weight_below_consumed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    created = client.post("/api/purchases", json=lot_payload()).json()
    lot_id = created["id"]
    consume_lot(session_factory, lot_id, D("400.00"))

    response = client.put(
        f"/api/purchases/{lot_id}",
        json=lot_payload(weight_kg="300.00"),
    )

    assert response.status_code == 422, response.text
    assert D(client.get(f"/api/purchases/{lot_id}").json()["weight_kg"]) == D(
        "1000.00"
    )


def test_delete_rejects_lot_used_by_heat(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    created = client.post("/api/purchases", json=lot_payload()).json()
    lot_id = created["id"]
    consume_lot(session_factory, lot_id, D("100.00"))

    response = client.delete(f"/api/purchases/{lot_id}")

    assert response.status_code == 409, response.text
    assert client.get(f"/api/purchases/{lot_id}").status_code == 200


def test_gst_uses_the_configured_settings_rate(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        settings = session.get(Setting, 1)
        assert settings is not None
        settings.gst_rate = D("0.05")
        session.commit()

    response = client.post("/api/purchases", json=lot_payload())

    assert response.status_code == 201, response.text
    assert response.json()["gst_amount"] == "10000.00"


def test_empty_list_returns_an_empty_array(client: TestClient) -> None:
    response = client.get("/api/purchases")

    assert response.status_code == 200
    assert response.json() == []
