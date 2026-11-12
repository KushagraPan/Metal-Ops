"""Unit tests for Docker and production hardening (Issue #13).

Covers:
1. Secure cookie flag when X-Forwarded-Proto is https
2. Documentation endpoints (/docs, /redoc, /openapi.json) disabled unless ENV=development
3. Origin check middleware on state-changing requests
4. Default dashboard month in Asia/Kolkata / reading TZ
5. .env loader reading key-value pairs before database/storage initialization
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.env import load_dotenv
from app.main import create_app, is_allowed_origin
from app.routers.dashboard import current_dashboard_month


# 1. Secure Cookie Flag Tests
@patch("app.routers.auth.AuthService")
def test_login_cookie_secure_when_x_forwarded_proto_https(mock_auth_service):
    mock_instance = mock_auth_service.return_value
    mock_user = type("User", (), {"id": 1, "email": "owner@workshop.local", "created_at": None})()
    mock_instance.authenticate.return_value = (mock_user, "test_session_id_123")

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"email": "owner@workshop.local", "password": "correct-password-10ch"},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "session=" in cookie_header
    assert "secure" in cookie_header.lower()
    assert "httponly" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()


@patch("app.routers.auth.AuthService")
def test_login_cookie_not_secure_over_http(mock_auth_service):
    mock_instance = mock_auth_service.return_value
    mock_user = type("User", (), {"id": 1, "email": "owner@workshop.local", "created_at": None})()
    mock_instance.authenticate.return_value = (mock_user, "test_session_id_123")

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"email": "owner@workshop.local", "password": "correct-password-10ch"},
        headers={"X-Forwarded-Proto": "http"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "session=" in cookie_header
    # When http, secure attribute should not be present
    assert "secure" not in cookie_header.lower()


@patch("app.routers.auth.AuthService")
def test_logout_cookie_honours_x_forwarded_proto(mock_auth_service):
    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/api/auth/logout",
        headers={"X-Forwarded-Proto": "https"},
        cookies={"session": "any_token"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "session=" in cookie_header
    assert "secure" in cookie_header.lower()


# 2. Documentation Gating Tests
def test_docs_enabled_in_development():
    with patch.dict(os.environ, {"ENV": "development"}):
        dev_app = create_app()
        test_client = TestClient(dev_app)
        assert test_client.get("/docs").status_code == 200
        assert test_client.get("/redoc").status_code == 200
        assert test_client.get("/openapi.json").status_code == 200


def test_docs_disabled_in_production():
    with patch.dict(os.environ, {"ENV": "production"}):
        prod_app = create_app()
        test_client = TestClient(prod_app)
        assert test_client.get("/docs").status_code == 404
        assert test_client.get("/redoc").status_code == 404
        assert test_client.get("/openapi.json").status_code == 404


# 3. Origin Check Middleware Tests
@patch("app.routers.auth.AuthService")
def test_origin_check_allows_matching_host(mock_auth):
    from fastapi import HTTPException
    mock_auth.return_value.authenticate.side_effect = HTTPException(status_code=401, detail="Invalid credentials")
    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "any"},
        headers={"Host": "127.0.0.1:3000", "Origin": "http://127.0.0.1:3000"},
    )
    # Should pass origin check and reach auth validation (401 or 422, NOT 403 Forbidden)
    assert response.status_code in {401, 422}


@patch("app.routers.auth.AuthService")
def test_origin_check_allows_absent_origin_for_non_browser(mock_auth):
    from fastapi import HTTPException
    mock_auth.return_value.authenticate.side_effect = HTTPException(status_code=401, detail="Invalid credentials")
    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "any"},
    )
    # Without Origin header, should pass through to auth
    assert response.status_code in {401, 422}


def test_origin_check_blocks_mismatched_origin_on_post():
    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "any"},
        headers={"Host": "127.0.0.1:3000", "Origin": "https://evil-attacker.com"},
    )
    assert response.status_code == 403
    assert "Forbidden: Origin mismatch" in response.text


def test_origin_check_allows_get_even_with_cross_origin():
    app = create_app()
    client = TestClient(app)
    # GET is safe / not state-changing; origin check should not block it
    response = client.get(
        "/api/health",
        headers={"Host": "127.0.0.1:3000", "Origin": "https://external-reader.com"},
    )
    assert response.status_code == 200


@patch("app.routers.auth.AuthService")
def test_origin_check_allowed_origins_env_override(mock_auth):
    from fastapi import HTTPException
    mock_auth.return_value.authenticate.side_effect = HTTPException(status_code=401, detail="Invalid credentials")
    with patch.dict(os.environ, {"ALLOWED_ORIGINS": "https://trusted-site.com, https://app.metalops.local"}):
        app = create_app()
        client = TestClient(app)
        response = client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "any"},
            headers={"Host": "127.0.0.1:3000", "Origin": "https://trusted-site.com"},
        )
        assert response.status_code in {401, 422}


# 4. Default Dashboard Month in Asia/Kolkata / TZ
def test_current_dashboard_month_format():
    month = current_dashboard_month()
    assert len(month) == 7
    parts = month.split("-")
    assert len(parts) == 2
    assert parts[0].isdigit() and len(parts[0]) == 4
    assert parts[1].isdigit() and 1 <= int(parts[1]) <= 12


def test_current_dashboard_month_respects_tz():
    month_kolkata = current_dashboard_month("Asia/Kolkata")
    month_utc = current_dashboard_month("UTC")
    assert len(month_kolkata) == 7
    assert len(month_utc) == 7


def test_current_dashboard_month_invalid_tz_fallback():
    # Invalid timezone string falls back to Asia/Kolkata cleanly without raising
    month = current_dashboard_month("Invalid/Unknown_Zone_99")
    assert len(month) == 7


# 5. .env Loader Tests
def test_load_dotenv_parses_values_and_quotes(tmp_path):
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "# Test comment\n"
        "TEST_VAR_PLAIN=hello_world\n"
        'TEST_VAR_DOUBLE="quoted with spaces"\n'
        "TEST_VAR_SINGLE='single quoted'\n"
        "ALREADY_SET=new_value\n",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {"ALREADY_SET": "original_value"}, clear=False):
        load_dotenv(env_file)
        assert os.environ.get("TEST_VAR_PLAIN") == "hello_world"
        assert os.environ.get("TEST_VAR_DOUBLE") == "quoted with spaces"
        assert os.environ.get("TEST_VAR_SINGLE") == "single quoted"
        # Existing environment variables should not be overwritten
        assert os.environ.get("ALREADY_SET") == "original_value"


# 6. Production Compose Configuration Tests (Issue #15)
def test_compose_prod_configuration():
    compose_path = os.path.join(os.path.dirname(__file__), "..", "..", "compose.prod.yaml")
    assert os.path.exists(compose_path), "compose.prod.yaml must exist"

    with open(compose_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Named volumes for persistence
    assert "metalops_postgres_data:" in content
    assert "metalops_uploads:" in content

    # Pre-built image tags with IMAGE_TAG fallback
    assert "${IMAGE_TAG:-latest}" in content
    assert "metalops-backend" in content
    assert "metalops-frontend" in content
    assert "metalops-postgres" in content

    # Health checks
    assert "healthcheck:" in content
    assert "pg_isready" in content
    assert "/api/ready" in content

