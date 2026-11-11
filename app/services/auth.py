"""Authentication use cases, password hashing, and session management."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.users import UserRepository

logger = logging.getLogger(__name__)

# Session timeout limits (documented):
# - IDLE_TIMEOUT_SECONDS: Revoked after 30 minutes (1,800s) of inactivity.
# - ABSOLUTE_TIMEOUT_SECONDS: Revoked after 12 hours (43,200s) maximum lifetime regardless of activity.
DEFAULT_IDLE_TIMEOUT_SECONDS: float = 1800.0
DEFAULT_ABSOLUTE_TIMEOUT_SECONDS: float = 43200.0

# Pre-computed dummy hash to prevent timing attacks / user enumeration when email does not exist
DUMMY_PASSWORD_HASH: str = (
    "scrypt$131072$8$1$0123456789abcdef0123456789abcdef$"
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
)

DEFAULT_SCRYPT_N: int = 131072  # 2^17 per OWASP guidelines for new hashes
DEFAULT_SCRYPT_R: int = 8
DEFAULT_SCRYPT_P: int = 1
# OpenSSL scrypt default maxmem is 32 MB; n=131072 requires 128 MB working memory.
SCRYPT_MAXMEM: int = 256 * 1024 * 1024


@dataclass
class SessionData:
    user_id: int
    created_at: float
    last_accessed_at: float


def hash_password(
    password: str,
    n: int = DEFAULT_SCRYPT_N,
    r: int = DEFAULT_SCRYPT_R,
    p: int = DEFAULT_SCRYPT_P,
) -> str:
    """Hash password using scrypt with a random 16-byte salt and embedded cost parameters."""
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=SCRYPT_MAXMEM,
    )
    return f"scrypt${n}${r}${p}${salt.hex()}${key.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against scrypt or pbkdf2 hash using constant-time comparison."""
    try:
        parts = password_hash.split("$")
        if parts[0] == "scrypt":
            if len(parts) == 6:
                # scrypt$n$r$p$salt$hash
                n = int(parts[1])
                r = int(parts[2])
                p = int(parts[3])
                salt = bytes.fromhex(parts[4])
                expected = bytes.fromhex(parts[5])
            elif len(parts) == 4 and ("n=" in parts[1] or "r=" in parts[1]):
                # scrypt$n=16384,r=8,p=1$salt$hash
                params = dict(
                    item.split("=") for item in parts[1].split(",") if "=" in item
                )
                n = int(params.get("n", 16384))
                r = int(params.get("r", 8))
                p = int(params.get("p", 1))
                salt = bytes.fromhex(parts[2])
                expected = bytes.fromhex(parts[3])
            elif len(parts) == 3:
                # Legacy 3-part format: scrypt$salt$hash (implicitly n=16384, r=8, p=1)
                n = 16384
                r = 8
                p = 1
                salt = bytes.fromhex(parts[1])
                expected = bytes.fromhex(parts[2])
            else:
                return False

            computed = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=n,
                r=r,
                p=p,
                maxmem=SCRYPT_MAXMEM,
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
    """In-memory server session store with idle and absolute expiry limits."""

    def __init__(
        self,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT_SECONDS,
        absolute_timeout: float = DEFAULT_ABSOLUTE_TIMEOUT_SECONDS,
    ) -> None:
        self.idle_timeout = idle_timeout
        self.absolute_timeout = absolute_timeout
        self._sessions: dict[str, SessionData] = {}

    def create(self, user_id: int, now: float | None = None) -> str:
        current_time = now if now is not None else time.time()
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = SessionData(
            user_id=user_id,
            created_at=current_time,
            last_accessed_at=current_time,
        )
        return session_id

    def get_session_data(self, session_id: str | None) -> SessionData | None:
        if not session_id:
            return None
        return self._sessions.get(session_id)

    def get_user_id(self, session_id: str | None, now: float | None = None) -> int | None:
        if not session_id:
            return None
        data = self._sessions.get(session_id)
        if data is None:
            return None

        current_time = now if now is not None else time.time()

        # Check absolute timeout limit (12 hours)
        if current_time - data.created_at > self.absolute_timeout:
            self.invalidate(session_id)
            return None

        # Check idle timeout limit (30 minutes)
        if current_time - data.last_accessed_at > self.idle_timeout:
            self.invalidate(session_id)
            return None

        # Update last accessed time
        data.last_accessed_at = current_time
        return data.user_id

    def invalidate(self, session_id: str | None) -> None:
        if session_id:
            self._sessions.pop(session_id, None)

    def clear(self) -> None:
        self._sessions.clear()


session_store = SessionStore()


class LoginRateLimiter:
    """Tracks failed login attempts and rate limits repeated failures."""

    def __init__(self, max_attempts: int = 5, window_seconds: float = 300.0) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}

    def is_rate_limited(self, key: str, now: float | None = None) -> bool:
        current_time = now if now is not None else time.time()
        attempts = self._get_recent_attempts(key, current_time)
        return len(attempts) >= self.max_attempts

    def record_failure(self, key: str, now: float | None = None) -> None:
        current_time = now if now is not None else time.time()
        attempts = self._get_recent_attempts(key, current_time)
        attempts.append(current_time)
        self._failures[key] = attempts

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)

    def clear(self) -> None:
        self._failures.clear()

    def _get_recent_attempts(self, key: str, current_time: float) -> list[float]:
        cutoff = current_time - self.window_seconds
        return [t for t in self._failures.get(key, []) if t > cutoff]


from app.env import load_dotenv

login_rate_limiter = LoginRateLimiter()


def load_dotenv_if_present() -> None:
    """Read .env into os.environ if present and not already defined in environment."""
    load_dotenv()


def ensure_owner_account(session: Session) -> User | None:
    """Create or return owner account configured in environment variables.

    Refuses to create an owner account if password or email is empty or unset.
    """
    load_dotenv_if_present()
    owner_email = os.getenv("OWNER_EMAIL")
    if not owner_email or not owner_email.strip():
        return None

    repo = UserRepository(session)
    existing = repo.get_by_email(owner_email.strip())
    if existing is not None:
        return existing

    pwd_hash = os.getenv("OWNER_PASSWORD_HASH")
    if pwd_hash:
        pwd_hash = pwd_hash.strip()

    if not pwd_hash:
        raw_pwd = os.getenv("OWNER_PASSWORD")
        if raw_pwd is None or not raw_pwd.strip():
            # Refuse to create owner account from an empty password
            return None
        raw_pwd = raw_pwd.strip()
        if len(raw_pwd) < 10:
            logger.warning("OWNER_PASSWORD rejected: must be at least 10 characters.")
            return None
        pwd_hash = hash_password(raw_pwd)

    user = repo.create(email=owner_email.strip(), password_hash=pwd_hash)
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
        if user is None:
            # Perform dummy verification so timing does not leak whether email exists
            verify_password(password, DUMMY_PASSWORD_HASH)
            raise InvalidCredentials("Invalid email or password.")
        if not verify_password(password, user.password_hash):
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
