"""Integration test fixtures for PostgreSQL real database testing.

These fixtures run exclusively against PostgreSQL (started via 'make test-db-up').
They do NOT touch SQLite or data/metalops.db.
Auth bypass is disabled: requests authenticate through /api/auth/login.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.db import make_engine
from app.main import app
from app.models import Base, Setting, User
from app.routers.auth import require_session
from app.services.auth import hash_password, session_store
from app.storage import LocalStorage, get_storage
from app.db import get_session

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://metalops_test:metalops_test@127.0.0.1:5433/metalops_test"
)


def get_test_database_url() -> str:
    return os.getenv("TEST_DATABASE_URL") or DEFAULT_TEST_DATABASE_URL


TEST_DATABASE_URL = get_test_database_url()


def parse_db_url(url: str | None = None) -> dict[str, Any]:
    resolved = url or get_test_database_url()
    u = make_url(resolved)
    return {
        "host": u.host or "127.0.0.1",
        "port": u.port or 5432,
        "user": u.username or "metalops_test",
        "password": u.password or "",
        "database": u.database or "metalops_test",
    }


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: requires a real PostgreSQL database (issue #12)"
    )


def _check_postgres_connection(url: str | None = None) -> None:
    parsed = parse_db_url(url)
    host = parsed["host"]
    port = parsed["port"]
    user = parsed["user"]
    password = parsed["password"]
    database = parsed["database"]

    try:
        import psycopg

        conn = psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=database,
            connect_timeout=3,
        )
        conn.close()
    except Exception as exc:
        raise pytest.UsageError(
            f"PostgreSQL test database or Docker is unavailable at {host}:{port}. "
            f"Start it with 'make test-db-up' or check Docker. ({exc})"
        ) from exc


@pytest.fixture(scope="session")
def postgres_engine():
    """Session-scoped PostgreSQL engine pointing to test-only database."""
    url = get_test_database_url()
    _check_postgres_connection(url)
    engine = make_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def clean_postgres_db(postgres_engine) -> Iterator[None]:
    """Provide a clean PostgreSQL schema for each test."""
    user = parse_db_url(get_test_database_url())["user"]
    with postgres_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        conn.execute(text(f'GRANT ALL ON SCHEMA public TO "{user}";'))
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
) -> Iterator[Any]:
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

    base_url = os.getenv("BASE_URL")
    if base_url:
        import httpx
        with httpx.Client(base_url=base_url, follow_redirects=True, timeout=10.0) as client:
            login_res = client.post(
                "/api/auth/login",
                json={
                    "email": "owner@workshop.local",
                    "password": "owner_password_123",
                },
            )
            assert login_res.status_code == 200, f"Login failed against {base_url}: {login_res.text}"
            yield client
        return

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
