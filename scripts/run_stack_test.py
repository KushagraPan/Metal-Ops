"""Run integration test suite against the Docker Compose stack (Issue #13).

Passes BASE_URL and TEST_DATABASE_URL pointing to the Compose stack and its
published Postgres test port (5434).
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    env = os.environ.copy()
    env["BASE_URL"] = os.getenv("BASE_URL", "http://127.0.0.1:3000")
    env["TEST_DATABASE_URL"] = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://metalops:metalops_demo_password@127.0.0.1:5434/metalops",
    )
    cmd = [sys.executable, "-m", "pytest", "tests/integration", "-v"]
    print(f"Running stack integration suite against {env['BASE_URL']} and {env['TEST_DATABASE_URL']}...")
    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
