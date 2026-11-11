"""Authentication use cases, password hashing, and session management."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.users import UserRepository


def hash_password(password: str) -> str:
    """Hash password using scrypt with a random 16-byte salt."""
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against scrypt or pbkdf2 hash using constant-time comparison."""
    try:
        parts = password_hash.split("$")
        if len(parts) == 3 and parts[0] == "scrypt":
            salt = bytes.fromhex(parts[1])
            expected = bytes.fromhex(parts[2])
            computed = hashlib.scrypt(
                password.encode("utf-8"), salt=salt, n=16384, r=8, p=1
            )
            return hmac.compare_digest(expected, computed)
        elif len(parts) == 3 and parts[0] == "pbkdf2_sha256":
            salt = bytes.fromhex(parts[1])
            expected = bytes.fromhex(parts[2])
            computed = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt, 600_000
            )
            return hmac.compare_digest(expected, computed)
        return False
    except Exception:
        return False


class SessionStore:
    """In-memory server session store mapping opaque tokens to user IDs."""

    def __init__(self) -> None:
        self._sessions: dict[str, int] = {}

    def create(self, user_id: int) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = user_id
        return session_id

    def get_user_id(self, session_id: str | None) -> int | None:
        if not session_id:
            return None
        return self._sessions.get(session_id)

    def invalidate(self, session_id: str | None) -> None:
        if session_id:
            self._sessions.pop(session_id, None)

    def clear(self) -> None:
        self._sessions.clear()


session_store = SessionStore()


def ensure_owner_account(session: Session) -> User | None:
    """Create or return owner account configured in environment variables."""
    owner_email = os.getenv("OWNER_EMAIL")
    if not owner_email:
        return None

    repo = UserRepository(session)
    existing = repo.get_by_email(owner_email)
    if existing is not None:
        return existing

    pwd_hash = os.getenv("OWNER_PASSWORD_HASH")
    if not pwd_hash:
        raw_pwd = os.getenv("OWNER_PASSWORD", "metalops123")
        pwd_hash = hash_password(raw_pwd)

    user = repo.create(email=owner_email, password_hash=pwd_hash)
    session.commit()
    return user


class AuthError(Exception):
    pass


class InvalidCredentials(AuthError):
    pass


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    def authenticate(self, email: str, password: str) -> tuple[User, str]:
        user = self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentials("Invalid email or password.")
        session_id = session_store.create(user.id)
        return user, session_id

    def logout(self, session_id: str | None) -> None:
        session_store.invalidate(session_id)

    def get_user_for_session(self, session_id: str | None) -> User | None:
        user_id = session_store.get_user_id(session_id)
        if user_id is None:
            return None
        return self.users.get_by_id(user_id)
