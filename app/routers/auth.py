"""Authentication HTTP endpoints and session dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.user import User
from app.schemas.auth import LoginInput, UserRead
from app.services.auth import AuthService, InvalidCredentials, login_rate_limiter

SESSION_COOKIE_NAME = "session"

SessionDep = Annotated[Session, Depends(get_session)]

public_router = APIRouter(prefix="/auth", tags=["auth"])
router = APIRouter(prefix="/auth", tags=["auth"])


def get_session_token(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        return token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :].strip()
    return None


def require_session(request: Request, session: SessionDep) -> User:
    token = get_session_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    user = AuthService(session).get_user_for_session(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
        )
    return user


CurrentUser = Annotated[User, Depends(require_session)]


@public_router.post("/login", response_model=UserRead)
def login(
    payload: LoginInput,
    request: Request,
    response: Response,
    session: SessionDep,
) -> UserRead:
    rate_key = payload.email.strip().lower()
    if login_rate_limiter.is_rate_limited(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
        )

    try:
        user, session_id = AuthService(session).authenticate(
            email=payload.email,
            password=payload.password,
        )
    except InvalidCredentials:
        login_rate_limiter.record_failure(rate_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    login_rate_limiter.reset(rate_key)

    # Cookie flags: HttpOnly, SameSite=Lax, Secure when served over HTTPS (documented for #13)
    is_secure = (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        path="/",
    )
    return UserRead.model_validate(user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session: SessionDep,
    _current_user: CurrentUser,
) -> dict[str, bool]:
    token = get_session_token(request)
    AuthService(session).logout(token)
    is_secure = (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=is_secure,
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
