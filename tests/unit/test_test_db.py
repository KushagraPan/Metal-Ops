"""Unit tests for test database URL parsing and connection checking."""

from __future__ import annotations

import pytest

from scripts.test_db import parse_db_url as script_parse_db_url
from tests.integration.conftest import (
    _check_postgres_connection,
    parse_db_url as conftest_parse_db_url,
)


def test_parse_db_url_default_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    for parse_fn in (script_parse_db_url, conftest_parse_db_url):
        cfg = parse_fn()
        assert cfg["host"] == "127.0.0.1"
        assert cfg["port"] == 5433
        assert cfg["user"] == "metalops_test"
        assert cfg["password"] == "metalops_test"
        assert cfg["database"] == "metalops_test"


def test_parse_db_url_custom_env(monkeypatch: pytest.MonkeyPatch) -> None:
    custom_url = "postgresql+psycopg://ci_user:ci_secret@postgres-ci:5432/ci_db"
    monkeypatch.setenv("TEST_DATABASE_URL", custom_url)

    for parse_fn in (script_parse_db_url, conftest_parse_db_url):
        cfg = parse_fn()
        assert cfg["host"] == "postgres-ci"
        assert cfg["port"] == 5432
        assert cfg["user"] == "ci_user"
        assert cfg["password"] == "ci_secret"
        assert cfg["database"] == "ci_db"


def test_parse_db_url_explicit_argument() -> None:
    custom_url = "postgresql+psycopg://user_x:pass_x@compose_db:5439/metal_custom"

    for parse_fn in (script_parse_db_url, conftest_parse_db_url):
        cfg = parse_fn(custom_url)
        assert cfg["host"] == "compose_db"
        assert cfg["port"] == 5439
        assert cfg["user"] == "user_x"
        assert cfg["password"] == "pass_x"
        assert cfg["database"] == "metal_custom"


def test_parse_db_url_default_port_when_omitted() -> None:
    url_without_port = "postgresql+psycopg://user_y:pass_y@db-host/dbname"

    for parse_fn in (script_parse_db_url, conftest_parse_db_url):
        cfg = parse_fn(url_without_port)
        assert cfg["host"] == "db-host"
        assert cfg["port"] == 5432
        assert cfg["user"] == "user_y"
        assert cfg["password"] == "pass_y"
        assert cfg["database"] == "dbname"


def test_check_postgres_connection_failure_loud_message_with_host_and_port() -> None:
    bad_url = "postgresql+psycopg://nobody:secret@127.0.0.1:54999/nodb"
    with pytest.raises(pytest.UsageError) as exc_info:
        _check_postgres_connection(bad_url)

    msg = str(exc_info.value)
    assert "PostgreSQL test database or Docker is unavailable at 127.0.0.1:54999." in msg
    assert "Start it with 'make test-db-up' or check Docker." in msg

