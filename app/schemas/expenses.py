"""Monthly fixed expense schemas."""

from __future__ import annotations

from decimal import Decimal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


MONTH_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    month: str = Field(min_length=7, max_length=7)
    category: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(ge=0, decimal_places=2)

    @field_validator("month")
    @classmethod
    def validate_month_format(cls, value: str) -> str:
        if not MONTH_REGEX.match(value):
            raise ValueError("month must be in YYYY-MM format")
        return value


class ExpenseUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    category: str | None = Field(default=None, min_length=1, max_length=100)
    amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)


class ExpenseRead(BaseModel):
    id: int
    month: str
    category: str
    amount: Decimal

