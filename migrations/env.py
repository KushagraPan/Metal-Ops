"""Alembic environment.

The URL comes from `DATABASE_URL` when set, otherwise from alembic.ini. Tests
override `sqlalchemy.url` in the Alembic Config, so no environment variable is
needed to migrate a temporary database.
"""

from __future__ import annotations

import os

from alembic import context

from app.db import make_engine
from app.models import Base

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    return os.getenv("DATABASE_URL") or configured or "sqlite:///./data/metalops.db"


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(database_url())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
