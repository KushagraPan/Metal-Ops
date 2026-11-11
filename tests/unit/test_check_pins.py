"""Unit tests for check_pins.py script."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.check_pins import (
    check_requirements,
    check_package_json,
    check_all,
)


def test_check_requirements_passes_for_exact_pinned_versions() -> None:
    content = """
    fastapi==0.115.6
    psycopg[binary]==3.2.3
    # Comment line
    uvicorn==0.34.0
    """
    errors = check_requirements(content)
    assert errors == []


def test_check_requirements_fails_for_ranges_or_unpinned() -> None:
    content = """
    fastapi>=0.115.0
    uvicorn~=0.34.0
    httpx
    alembic<=1.14.0
    psycopg!=3.0.0
    """
    errors = check_requirements(content)
    assert len(errors) == 5
    assert any("fastapi" in e for e in errors)
    assert any("uvicorn" in e for e in errors)
    assert any("httpx" in e for e in errors)
    assert any("alembic" in e for e in errors)
    assert any("psycopg" in e for e in errors)


def test_check_package_json_passes_for_exact_versions() -> None:
    data = {
        "dependencies": {
            "react": "18.3.1",
            "clsx": "2.1.1",
        },
        "devDependencies": {
            "vite": "8.3.4",
            "typescript": "5.9.3",
        },
    }
    errors = check_package_json(data)
    assert errors == []


def test_check_package_json_fails_for_caret_tilde_or_ranges() -> None:
    data = {
        "dependencies": {
            "react": "^18.3.1",
            "clsx": "~2.1.1",
            "lucide-react": "*",
            "recharts": ">=2.15.0",
        },
        "devDependencies": {
            "vite": "latest",
        },
    }
    errors = check_package_json(data)
    assert len(errors) == 5
    assert any("react" in e for e in errors)
    assert any("clsx" in e for e in errors)
    assert any("lucide-react" in e for e in errors)
    assert any("recharts" in e for e in errors)
    assert any("vite" in e for e in errors)


def test_check_all_passes_for_current_repo() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    errors = check_all(repo_root)
    assert errors == [], f"Found unpinned dependencies: {errors}"

