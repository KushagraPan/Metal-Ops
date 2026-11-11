"""Authentication request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr


class LoginInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
