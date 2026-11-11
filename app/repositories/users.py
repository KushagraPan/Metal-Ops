"""Persistence queries for user accounts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.strip().lower())
        return self.session.scalar(stmt)

    def create(self, *, email: str, password_hash: str) -> User:
        user = User(email=email.strip().lower(), password_hash=password_hash)
        self.session.add(user)
        self.session.flush()
        return user
