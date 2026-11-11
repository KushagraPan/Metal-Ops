"""Lifecycle and connection manager for the integration test database.

Usage:
    python scripts/test_db.py up      # Start the throwaway PostgreSQL container
    python scripts/test_db.py down    # Stop and remove the test container
    python scripts/test_db.py check   # Verify PostgreSQL connection; fail if unavailable
    python scripts/test_db.py url     # Print the test database URL
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any

from sqlalchemy.engine import make_url

CONTAINER_NAME = "metalops-test-postgres"
IMAGE = "postgres:16-alpine"
DEFAULT_PORT = 5433
DEFAULT_USER = "metalops_test"
DEFAULT_PASSWORD = "metalops_test"
DEFAULT_DB = "metalops_test"
DEFAULT_HOST = "127.0.0.1"

DEFAULT_TEST_DATABASE_URL = (
    f"postgresql+psycopg://{DEFAULT_USER}:{DEFAULT_PASSWORD}@{DEFAULT_HOST}:{DEFAULT_PORT}/{DEFAULT_DB}"
)


def get_test_database_url() -> str:
    return os.getenv("TEST_DATABASE_URL") or DEFAULT_TEST_DATABASE_URL


def parse_db_url(url: str | None = None) -> dict[str, Any]:
    resolved = url or get_test_database_url()
    u = make_url(resolved)
    return {
        "host": u.host or DEFAULT_HOST,
        "port": u.port or 5432,
        "user": u.username or DEFAULT_USER,
        "password": u.password or DEFAULT_PASSWORD,
        "database": u.database or DEFAULT_DB,
    }


def run_cmd(args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, capture_output=True, text=True, check=check
    )


def is_docker_running() -> bool:
    res = run_cmd(["docker", "info"])
    return res.returncode == 0


def is_container_running() -> bool:
    res = run_cmd(
        ["docker", "ps", "-q", "-f", f"name=^{CONTAINER_NAME}$"]
    )
    return res.returncode == 0 and bool(res.stdout.strip())


def is_container_present() -> bool:
    res = run_cmd(
        ["docker", "ps", "-a", "-q", "-f", f"name=^{CONTAINER_NAME}$"]
    )
    return res.returncode == 0 and bool(res.stdout.strip())


def wait_for_postgres(timeout_seconds: int = 20, url: str | None = None) -> bool:
    config = parse_db_url(url)
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            import psycopg

            conn = psycopg.connect(
                host=config["host"],
                port=config["port"],
                user=config["user"],
                password=config["password"],
                dbname=config["database"],
                connect_timeout=2,
            )
            conn.close()
            return True
        except Exception:
            time.sleep(0.5)
    return False


def cmd_up() -> None:
    if not is_docker_running():
        sys.stderr.write(
            "Docker is unavailable. Please ensure Docker Desktop is running.\n"
        )
        sys.exit(1)

    config = parse_db_url()
    host = config["host"]
    port = config["port"]
    user = config["user"]
    password = config["password"]
    database = config["database"]

    if is_container_running():
        if wait_for_postgres(timeout_seconds=5):
            print(f"Container '{CONTAINER_NAME}' is already running and ready at {host}:{port}.")
            return

    if is_container_present():
        run_cmd(["docker", "start", CONTAINER_NAME])
    else:
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "-e",
            f"POSTGRES_USER={user}",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            "-e",
            f"POSTGRES_DB={database}",
            "-p",
            f"{host}:{port}:5432",
            IMAGE,
        ]
        res = run_cmd(cmd)
        if res.returncode != 0:
            sys.stderr.write(f"Failed to start container: {res.stderr}\n")
            sys.exit(res.returncode)

    if not wait_for_postgres(timeout_seconds=25):
        sys.stderr.write(
            f"PostgreSQL container '{CONTAINER_NAME}' started but did not become ready in time.\n"
        )
        sys.exit(1)

    print(f"PostgreSQL test database ready at {get_test_database_url()}")


def cmd_down() -> None:
    if not is_docker_running():
        return
    if is_container_present():
        run_cmd(["docker", "stop", CONTAINER_NAME])
        run_cmd(["docker", "rm", "-f", CONTAINER_NAME])
        print(f"Container '{CONTAINER_NAME}' stopped and removed.")


def cmd_check() -> None:
    config = parse_db_url()
    host = config["host"]
    port = config["port"]
    if not wait_for_postgres(timeout_seconds=3):
        sys.stderr.write(
            f"PostgreSQL test database or Docker is unavailable at {host}:{port}. "
            "Start it with 'make test-db-up' or check Docker.\n"
        )
        sys.exit(1)
    print(f"PostgreSQL test database is available at {get_test_database_url()}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_db.py [up|down|check|url]")
        sys.exit(1)
    command = sys.argv[1].lower()
    if command == "up":
        cmd_up()
    elif command == "down":
        cmd_down()
    elif command == "check":
        cmd_check()
    elif command == "url":
        print(get_test_database_url())
    else:
        sys.stderr.write(f"Unknown command: {command}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
