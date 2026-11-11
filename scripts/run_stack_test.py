"""Run integration test suite against the Docker Compose stack (Issue #13).

Passes BASE_URL and TEST_DATABASE_URL pointing to the Compose stack and its
published Postgres test port (5434). Loads .env via app.env.load_dotenv() and
constructs TEST_DATABASE_URL from POSTGRES_PASSWORD with no hardcoded fallback.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.env import load_dotenv


def main() -> None:
    load_dotenv()
    env = os.environ.copy()
    env["BASE_URL"] = os.getenv("BASE_URL", "http://127.0.0.1:3000")

    if "TEST_DATABASE_URL" not in env or not env["TEST_DATABASE_URL"]:
        password = env.get("POSTGRES_PASSWORD")
        if not password:
            raise RuntimeError(
                "POSTGRES_PASSWORD is not set in environment or .env; cannot construct TEST_DATABASE_URL"
            )
        user = env.get("POSTGRES_USER", "metalops")
        db = env.get("POSTGRES_DB", "metalops")
        env["TEST_DATABASE_URL"] = (
            f"postgresql+psycopg://{user}:{password}@127.0.0.1:5434/{db}"
        )

    cmd = [sys.executable, "-m", "pytest", "tests/integration", "-v"]
    print(f"Running stack integration suite against {env['BASE_URL']} and {env['TEST_DATABASE_URL']}...")
    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
