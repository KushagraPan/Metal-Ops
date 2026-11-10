"""Delete the local dev SQLite database before reseeding.

Used by `make reset-db`. The script refuses to run when `DATABASE_URL` points
anywhere other than `data/metalops.db`, so it cannot delete a shared or
production database by accident.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
DEV_DB = ROOT / "data" / "metalops.db"
DEFAULT_URL = "sqlite:///./data/metalops.db"
SIDECARS = ("-wal", "-shm", "-journal")


def dev_database_path() -> Path:
    """Return the dev database path, or refuse an unsafe configuration."""
    configured = os.getenv("DATABASE_URL")
    url = make_url(configured or DEFAULT_URL)

    if url.get_backend_name() != "sqlite":
        raise SystemExit(
            f"Refusing to reset non-SQLite DATABASE_URL: {url!s}"
        )
    if not url.database or url.database == ":memory:":
        raise SystemExit("Refusing to reset an in-memory database.")

    candidate = Path(url.database)
    if not candidate.is_absolute():
        candidate = ROOT / candidate

    if DEV_DB.is_symlink() or DEV_DB.parent.is_symlink():
        raise SystemExit("Refusing to reset a symlinked dev database path.")
    if candidate.resolve() != DEV_DB.resolve():
        raise SystemExit(
            f"Refusing to reset {candidate.resolve()}; "
            f"the dev database is {DEV_DB.resolve()}."
        )
    return DEV_DB


def main() -> int:
    path = dev_database_path()
    removed: list[str] = []

    for target in (
        path,
        *(Path(f"{path}{suffix}") for suffix in SIDECARS),
    ):
        if target.exists():
            try:
                target.unlink()
            except PermissionError:
                raise SystemExit(
                    f"Could not delete {target}. "
                    "Stop any running dev server and retry."
                ) from None
            removed.append(target.name)

    if removed:
        print(f"removed dev database files: {', '.join(removed)}")
    else:
        print("dev database file not present; nothing to delete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
