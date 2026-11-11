"""Integration test fixtures for PostgreSQL real database testing.

These fixtures run exclusively against PostgreSQL (started via 'make test-db-up').
They do NOT touch SQLite or data/metalops.db.
Auth bypass is disabled: requests authenticate through /api/auth/login.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.db import make_engine
from app.main import app
from app.models import Base, Setting, User
from app.routers.auth import require_session
from app.services.auth import hash_password, session_store
from app.storage import LocalStorage, get_storage
from app.db import get_session

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://metalops_test:metalops_test@127.0.0.1:5433/metalops_test",
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: requires a real PostgreSQL database (issue #12)"
    )


def _check_postgres_connection() -> None:
    try:
        import psycopg

        conn = psycopg.connect(
            "host=127.0.0.1 port=5433 user=metalops_test password=metalops_test dbname=metalops_test connect_timeout=3"
        )
        conn.close()
    except Exception as exc:
        raise pytest.UsageError(
            f"PostgreSQL test database or Docker is unavailable at 127.0.0.1:5433. "
            f"Start it with 'make test-db-up' or check Docker. ({exc})"
        ) from exc


@pytest.fixture(scope="session")
def postgres_engine():
    """Session-scoped PostgreSQL engine pointing to test-only database."""
    _check_postgres_connection()
    engine = make_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def clean_postgres_db(postgres_engine) -> Iterator[None]:
    """Provide a clean PostgreSQL schema for each test."""
    with postgres_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO metalops_test;"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))

    Base.metadata.create_all(postgres_engine)
    yield


@pytest.fixture
def postgres_session_factory(postgres_engine, clean_postgres_db) -> sessionmaker[Session]:
    return sessionmaker(bind=postgres_engine, class_=Session, expire_on_commit=False)


@pytest.fixture
def postgres_session(postgres_session_factory) -> Iterator[Session]:
    with postgres_session_factory() as session:
        yield session


@pytest.fixture
def test_storage(tmp_path: Path) -> LocalStorage:
    storage_dir = tmp_path / "integration_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return LocalStorage(storage_dir)


@pytest.fixture
def auth_client(
    postgres_session_factory: sessionmaker[Session],
    test_storage: LocalStorage,
) -> Iterator[TestClient]:
    """TestClient authenticated via real /api/auth/login against PostgreSQL."""
    session_store.clear()

    # Create owner account & default settings
    with postgres_session_factory() as session:
        owner = User(
            email="owner@workshop.local",
            password_hash=hash_password("owner_password_123"),
        )
        session.add(owner)
        session.add(Setting(id=1, gst_rate=0.18, planned_yield_pct=89.0))
        session.commit()

    def override_get_session() -> Iterator[Session]:
        with postgres_session_factory() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_storage] = lambda: test_storage

    # Ensure no lingering auth bypass
    app.dependency_overrides.pop(require_session, None)

    try:
        with TestClient(app) as client:
            login_res = client.post(
                "/api/auth/login",
                json={
                    "email": "owner@workshop.local",
                    "password": "owner_password_123",
                },
            )
            assert login_res.status_code == 200, f"Login failed: {login_res.text}"
            yield client
    finally:
        app.dependency_overrides.clear()
        session_store.clear()

