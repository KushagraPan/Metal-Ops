from decimal import Decimal
from collections.abc import Iterator
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session, make_engine
from app.main import app
from app.models import Base, Setting

D = Decimal


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = make_engine(f"sqlite:///{(tmp_path / 'expenses.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with factory() as session:
        session.add(Setting(id=1, gst_rate=D("0.18"), planned_yield_pct=D("89.00")))
        session.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_create_expense_and_list_by_month(client: TestClient) -> None:
    res1 = client.post(
        "/api/expenses",
        json={"month": "2026-10", "category": "Rent", "amount": "35000.00"},
    )
    assert res1.status_code == 201, res1.text
    data1 = res1.json()
    assert data1["month"] == "2026-10"
    assert data1["category"] == "Rent"
    assert data1["amount"] == "35000.00"

    res2 = client.post(
        "/api/expenses",
        json={"month": "2026-11", "category": "Salaries", "amount": "120000.00"},
    )
    assert res2.status_code == 201, res2.text

    # Filter by month
    oct_res = client.get("/api/expenses", params={"month": "2026-10"})
    assert oct_res.status_code == 200
    assert len(oct_res.json()) == 1
    assert oct_res.json()[0]["category"] == "Rent"

    nov_res = client.get("/api/expenses", params={"month": "2026-11"})
    assert nov_res.status_code == 200
    assert len(nov_res.json()) == 1
    assert nov_res.json()[0]["category"] == "Salaries"


def test_expense_validations(client: TestClient) -> None:
    # Negative amount
    res = client.post(
        "/api/expenses",
        json={"month": "2026-10", "category": "Rent", "amount": "-100.00"},
    )
    assert res.status_code == 422

    # Invalid month format
    res = client.post(
        "/api/expenses",
        json={"month": "2026/10", "category": "Rent", "amount": "100.00"},
    )
    assert res.status_code == 422

    # Blank category
    res = client.post(
        "/api/expenses",
        json={"month": "2026-10", "category": "   ", "amount": "100.00"},
    )
    assert res.status_code == 422


def test_update_and_delete_expense(client: TestClient) -> None:
    create = client.post(
        "/api/expenses",
        json={"month": "2026-10", "category": "Rent", "amount": "35000.00"},
    ).json()
    exp_id = create["id"]

    # Update
    update_res = client.put(
        f"/api/expenses/{exp_id}",
        json={"category": "Office Rent", "amount": "40000.00"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["category"] == "Office Rent"
    assert update_res.json()["amount"] == "40000.00"

    # Delete
    del_res = client.delete(f"/api/expenses/{exp_id}")
    assert del_res.status_code == 204

    # Now 404
    assert client.get(f"/api/expenses/{exp_id}").status_code == 404
    assert client.delete(f"/api/expenses/{exp_id}").status_code == 404

