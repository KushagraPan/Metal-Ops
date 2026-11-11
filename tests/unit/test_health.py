from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready_when_db_up() -> None:
    with TestClient(app) as client:
        response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_db_down() -> None:
    def failing_session():
        mock_session = MagicMock()
        mock_session.execute.side_effect = RuntimeError("Database connection unreachable")
        yield mock_session

    app.dependency_overrides[get_session] = failing_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/ready")

        assert response.status_code == 503
        assert "Database unavailable" in response.text
    finally:
        app.dependency_overrides.pop(get_session, None)
