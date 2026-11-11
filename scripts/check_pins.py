#!/usr/bin/env python3
"""Check that all dependencies in requirements.txt and package.json are pinned to exact versions."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Match an exact pip version pin like package==1.2.3 or pkg[extra]==1.2.3
# Disallows >=, <=, ~=, !=, >, <, or bare package names.
PIP_EXACT_PIN_RE = re.compile(
    r"^[a-zA-Z0-9_\-\.\[\]]+\s*==\s*[a-zA-Z0-9_\-\.\+]+$"
)

# Match an exact npm semver like 1.2.3 or 1.2.3-alpha.1
# Disallows ^, ~, *, >=, <=, >, <, latest, x, ||, etc.
NPM_EXACT_PIN_RE = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9a-zA-Z_\-\.]+)?(?:\+[0-9a-zA-Z_\-\.]+)?$"
)


def check_requirements(content: str) -> list[str]:
    """Check requirements.txt content for exact pinned versions (==)."""
    errors: list[str] = []
    lines = content.splitlines()

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Strip inline comments
        if " #" in line:
            line = line.split(" #", 1)[0].strip()

        if not PIP_EXACT_PIN_RE.match(line):
            errors.append(
                f"requirements.txt line {idx}: '{raw_line.strip()}' is not pinned with exact '=='"
            )

    return errors


def check_package_json(data_or_content: dict[str, Any] | str) -> list[str]:
    """Check package.json dependencies and devDependencies for exact pinned versions."""
    if isinstance(data_or_content, str):
        data = json.loads(data_or_content)
    else:
        data = data_or_content

    errors: list[str] = []
    for dep_type in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        deps = data.get(dep_type, {})
        if not isinstance(deps, dict):
            continue

        for pkg, version in deps.items():
            version_str = str(version).strip()
            if not NPM_EXACT_PIN_RE.match(version_str):
                errors.append(
                    f"package.json {dep_type}.{pkg}: '{version_str}' is not an exact version (must not use ^, ~, ranges, or tags)"
                )

    return errors


def check_all(repo_root: Path | None = None) -> list[str]:
    """Check both requirements.txt and frontend/package.json in the repository."""
    root = repo_root or Path(__file__).resolve().parents[1]
    all_errors: list[str] = []

    req_path = root / "requirements.txt"
    if req_path.is_file():
        req_errors = check_requirements(req_path.read_text(encoding="utf-8"))
        all_errors.extend(req_errors)
    else:
        all_errors.append(f"Missing file: {req_path}")

    pkg_path = root / "frontend" / "package.json"
    if pkg_path.is_file():
        pkg_errors = check_package_json(pkg_path.read_text(encoding="utf-8"))
        all_errors.extend(pkg_errors)
    else:
        all_errors.append(f"Missing file: {pkg_path}")

    return all_errors


def main() -> None:
    errors = check_all()
    if errors:
        sys.stderr.write("Pin check FAILED: unpinned dependencies detected:\n")
        for err in errors:
            sys.stderr.write(f"  - {err}\n")
        sys.exit(1)

    print("Pin check PASSED: all dependencies in requirements.txt and package.json are exactly pinned.")
    sys.exit(0)


if __name__ == "__main__":
    main()

