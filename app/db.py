"""Database engine and session factory.

`DATABASE_URL` selects the database. The default is a file-backed SQLite
database under `data/`, which is git-ignored. PostgreSQL is used only when the
environment provides a URL, for example in Docker.

SQLite does not enforce foreign keys unless asked, so the connection listener
below turns them on. That makes local behaviour match PostgreSQL.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./data/metalops.db"


def database_url() -> str:
    return os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL


def _is_sqlite(url: str) -> bool:
    return make_url(url).get_backend_name() == "sqlite"


def _ensure_sqlite_directory(url: str) -> None:
    database = make_url(url).database
    if not database or database == ":memory:":
        return
    Path(database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _enable_sqlite_foreign_keys(
    dbapi_connection: Any, _connection_record: Any
) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url: str | None = None) -> Engine:
    resolved = url or database_url()
    if _is_sqlite(resolved):
        _ensure_sqlite_directory(resolved)
    engine = create_engine(
        resolved,
        connect_args={"check_same_thread": False} if _is_sqlite(resolved) else {},
        pool_pre_ping=True,
    )
    if _is_sqlite(resolved):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
