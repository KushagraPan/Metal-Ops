"""Environment variable and .env loader.

Ensures that variables defined in .env (such as DATABASE_URL, STORAGE_DIR,
OWNER_EMAIL, OWNER_PASSWORD, ENV, SEED_DEMO) are loaded into os.environ
before database engine or storage subsystems initialize.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Read key-value pairs from a .env file into os.environ if not already set."""
    env_file = Path(path)
    if not env_file.is_file():
        return
    try:
        content = env_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            if (v.startswith('"') and v.endswith('"')) or (
                v.startswith("'") and v.endswith("'")
            ):
                v = v[1:-1]
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


# Automatically load .env on initial import if present
load_dotenv()
