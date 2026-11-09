from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.sql.sqltypes import Float, Numeric

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "alembic_version",
    "settings",
    "users",
    "purchase_lots",
    "heats",
    "heat_inputs",
    "sales",
    "spectro_reports",
    "monthly_expenses",
}

# Columns that hold money, weights, or percentages. None may be FLOAT.
NUMERIC_COLUMNS = {
    "settings": ["gst_rate", "planned_yield_pct"],
    "purchase_lots": ["weight_kg", "rate_per_kg", "transport_cost"],
    "heats": [
        "duration_hours",
        "output_kg",
        "dross_kg",
        "iron_scrap_kg",
        "oil_cost",
        "power_cost",
        "labour_cost",
        "other_cost",
    ],
    "heat_inputs": ["kg"],
    "sales": ["weight_kg", "rate_per_kg", "transport_cost", "transport_billed"],
    "monthly_expenses": ["amount"],
}


def upgrade(db_path: Path) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(config, "head")


def test_one_migration_creates_every_table_on_fresh_sqlite(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_path = tmp_path / "fresh.db"

    upgrade(db_path)

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES

    with engine.connect() as connection:
        versions = connection.execute(text("select version_num from alembic_version")).scalars().all()
    assert len(versions) == 1


def test_money_and_weight_columns_use_numeric(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_path = tmp_path / "types.db"

    upgrade(db_path)

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    inspector = inspect(engine)

    for table, column_names in NUMERIC_COLUMNS.items():
        columns = {column["name"]: column["type"] for column in inspector.get_columns(table)}
        for name in column_names:
            column_type = columns[name]
            assert isinstance(column_type, Numeric), f"{table}.{name} is {column_type!r}"
            assert not isinstance(column_type, Float), f"{table}.{name} must not be FLOAT"
