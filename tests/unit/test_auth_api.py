import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session, make_engine
from app.main import app
from app.models import Base, User
from app.services.auth import hash_password, verify_password, session_store, ensure_owner_account


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = make_engine(f"sqlite:///{(tmp_path / 'auth.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
) -> Iterator[TestClient]:
    session_store.clear()
    def override_get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        session_store.clear()


def test_health_does_not_require_session(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_protected_routes_return_401_without_session(client: TestClient) -> None:
    routes = [
        ("GET", "/api/purchases"),
        ("POST", "/api/purchases"),
        ("GET", "/api/heats"),
        ("POST", "/api/heats"),
        ("GET", "/api/sales"),
        ("POST", "/api/sales"),
        ("GET", "/api/expenses?month=2026-10"),
        ("GET", "/api/dashboard?month=2026-10"),
        ("GET", "/api/reports/1/download"),
        ("DELETE", "/api/reports/1"),
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/logout"),
    ]
    for method, path in routes:
        if method == "GET":
            res = client.get(path)
        elif method == "DELETE":
            res = client.delete(path)
        else:
            res = client.post(path, json={})
        assert res.status_code == 401, f"{method} {path} should return 401 without session, got {res.status_code}"


def test_login_success_and_authenticated_request_flow(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    # Seed user with hashed password
    with session_factory() as session:
        user = User(
            email="owner@workshop.local",
            password_hash=hash_password("FurnaceSecret123"),
        )
        session.add(user)
        session.commit()

    # Login with valid credentials
    login_res = client.post(
        "/api/auth/login",
        json={"email": "owner@workshop.local", "password": "FurnaceSecret123"},
    )
    assert login_res.status_code == 200, login_res.text
    assert "session" in client.cookies

    # Access protected route /api/auth/me with session cookie
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "owner@workshop.local"

    # Access protected route /api/purchases
    purchases_res = client.get("/api/purchases")
    assert purchases_res.status_code == 200


def test_login_with_invalid_credentials_returns_401(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        user = User(
            email="owner@workshop.local",
            password_hash=hash_password("FurnaceSecret123"),
        )
        session.add(user)
        session.commit()

    # Wrong password
    res = client.post(
        "/api/auth/login",
        json={"email": "owner@workshop.local", "password": "WrongPassword"},
    )
    assert res.status_code == 401
    assert "session" not in client.cookies

    # Non-existent user
    res2 = client.post(
        "/api/auth/login",
        json={"email": "stranger@workshop.local", "password": "FurnaceSecret123"},
    )
    assert res2.status_code == 401


def test_logout_invalidates_session(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        user = User(
            email="owner@workshop.local",
            password_hash=hash_password("FurnaceSecret123"),
        )
        session.add(user)
        session.commit()

    login_res = client.post(
        "/api/auth/login",
        json={"email": "owner@workshop.local", "password": "FurnaceSecret123"},
    )
    assert login_res.status_code == 200
    session_cookie = client.cookies.get("session")
    assert session_cookie is not None

    # Verify session works
    assert client.get("/api/auth/me").status_code == 200

    # Logout
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200

    # Verify me returns 401 now
    assert client.get("/api/auth/me").status_code == 401

    # Even if client maliciously sends old session cookie back, server invalidated it
    client.cookies.set("session", session_cookie)
    assert client.get("/api/auth/me").status_code == 401


def test_passwords_are_stored_hashed() -> None:
    raw = "MySecurePasswd!2026"
    hashed = hash_password(raw)
    assert hashed != raw
    assert hashed.startswith("scrypt$")
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_owner_account_created_from_env_vars(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OWNER_EMAIL", "boss@metalops.test")
    monkeypatch.setenv("OWNER_PASSWORD", "Factory2026#")

    with session_factory() as session:
        owner = ensure_owner_account(session)
        assert owner is not None
        assert owner.email == "boss@metalops.test"
        assert verify_password("Factory2026#", owner.password_hash) is True

        # Calling again should be idempotent and return existing
        owner_again = ensure_owner_account(session)
        assert owner_again.id == owner.id


def test_full_openapi_route_list_asserts_401_without_session(client: TestClient) -> None:
    schema = app.openapi()
    paths = schema.get("paths", {})
    assert paths, "OpenAPI schema must have paths"

    exempt_paths = {"/api/health", "/api/auth/login"}

    for path, path_item in paths.items():
        if path in exempt_paths:
            continue
        for method in ["get", "post", "put", "delete", "patch"]:
            if method not in path_item:
                continue
            # Replace path parameters with dummy integer id or date
            test_path = re.sub(r"\{[a-zA-Z0-9_]+\}", "1", path)
            response = client.request(method.upper(), test_path)
            assert (
                response.status_code == 401
            ), f"OpenAPI route {method.upper()} {path} (requested as {test_path}) must return 401 without session, got {response.status_code}"


def test_session_idle_and_absolute_expiry(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        user = User(
            email="timer@metalops.test",
            password_hash=hash_password("Pass123"),
        )
        session.add(user)
        session.commit()

    # Login
    res = client.post("/api/auth/login", json={"email": "timer@metalops.test", "password": "Pass123"})
    assert res.status_code == 200
    token = client.cookies.get("session")
    assert token is not None

    # Normal access works
    assert client.get("/api/auth/me").status_code == 200

    # Simulate idle timeout (advance last_accessed_at by > 1800s)
    session_data = session_store.get_session_data(token)
    assert session_data is not None
    session_data.last_accessed_at -= 1801
    assert client.get("/api/auth/me").status_code == 401

    # Login again
    res2 = client.post("/api/auth/login", json={"email": "timer@metalops.test", "password": "Pass123"})
    token2 = client.cookies.get("session")
    session_data2 = session_store.get_session_data(token2)
    assert session_data2 is not None

    # Simulate absolute timeout (advance created_at by > 43200s, even if active)
    session_data2.created_at -= 43201
    assert client.get("/api/auth/me").status_code == 401


def test_owner_account_refuses_empty_password(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OWNER_EMAIL", "empty_pw_owner@metalops.test")
    monkeypatch.setenv("OWNER_PASSWORD", "")
    monkeypatch.delenv("OWNER_PASSWORD_HASH", raising=False)

    with session_factory() as session:
        owner = ensure_owner_account(session)
        assert owner is None

    monkeypatch.setenv("OWNER_PASSWORD", "   ")
    with session_factory() as session:
        owner2 = ensure_owner_account(session)
        assert owner2 is None


def test_env_example_contains_placeholders_only() -> None:
    env_example_path = Path(".env.example")
    assert env_example_path.exists(), ".env.example must exist"
    lines = env_example_path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        assert val == "", f".env.example key '{key}' should only contain an empty placeholder, got '{val}'"


def test_failed_logins_return_same_message_and_are_rate_limited(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        user = User(
            email="ratelimit@metalops.test",
            password_hash=hash_password("RealPassword123"),
        )
        session.add(user)
        session.commit()

    # Unknown email
    res1 = client.post("/api/auth/login", json={"email": "unknown@test.local", "password": "any"})
    assert res1.status_code == 401
    assert res1.json() == {"detail": "Invalid email or password."}

    # Wrong password
    res2 = client.post("/api/auth/login", json={"email": "ratelimit@metalops.test", "password": "wrong"})
    assert res2.status_code == 401
    assert res2.json() == {"detail": "Invalid email or password."}

    # Trigger rate limit: default allows 5 attempts, 6th returns 429
    for _ in range(4):
        res = client.post("/api/auth/login", json={"email": "ratelimit@metalops.test", "password": "wrong"})
        assert res.status_code == 401

    # 6th attempt should return 429 Too Many Requests
    res_limited = client.post("/api/auth/login", json={"email": "ratelimit@metalops.test", "password": "wrong"})
    assert res_limited.status_code == 429
    assert "too many" in res_limited.text.lower() or "rate" in res_limited.text.lower()


def test_cookie_flags_httponly_samesite_and_secure_on_https(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        user = User(
            email="cookie@metalops.test",
            password_hash=hash_password("Pass123"),
        )
        session.add(user)
        session.commit()

    # Plain HTTP request
    res_http = client.post("/api/auth/login", json={"email": "cookie@metalops.test", "password": "Pass123"})
    assert res_http.status_code == 200
    cookie_header = res_http.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header
    assert "secure" not in cookie_header

    # HTTPS request (simulated via x-forwarded-proto or base_url)
    res_https = client.post(
        "/api/auth/login",
        json={"email": "cookie@metalops.test", "password": "Pass123"},
        headers={"x-forwarded-proto": "https"},
    )
    assert res_https.status_code == 200
    cookie_header_https = res_https.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie_header_https
    assert "samesite=lax" in cookie_header_https
    assert "secure" in cookie_header_https

