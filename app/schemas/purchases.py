"""Purchase lot request and response schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import GstMode, PurchaseTransportMode


class PurchaseLotInput(BaseModel):
    """Payload for creating or replacing a lot.

    `SUPPLIER_DELIVERS` normalises the freight to zero. `WE_PAY` requires a
    positive freight cost, because the cost would otherwise be meaningless.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    purchase_date: date
    supplier: str = Field(min_length=1, max_length=200)
    notes: str | None = None
    weight_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    rate_per_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    gst_mode: GstMode
    transport_mode: PurchaseTransportMode
    transport_cost: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )

    @field_validator("supplier")
    @classmethod
    def supplier_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("supplier must not be blank")
        return value

    @field_validator("notes")
    @classmethod
    def blank_notes_become_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def apply_transport_rules(self) -> PurchaseLotInput:
        if self.transport_mode == PurchaseTransportMode.SUPPLIER_DELIVERS:
            self.transport_cost = Decimal("0.00")
        elif self.transport_cost <= 0:
            raise ValueError(
                "transport_cost must be greater than 0 when WE_PAY"
            )
        return self


class PurchaseLotRead(BaseModel):
    """A lot plus the values derived by `calc.py`."""

    id: int
    purchase_date: date
    supplier: str
    notes: str | None
    weight_kg: Decimal
    rate_per_kg: Decimal
    gst_mode: GstMode
    transport_mode: PurchaseTransportMode
    transport_cost: Decimal
    gst_amount: Decimal
    landed_cost_per_kg: Decimal | None
    consumed_kg: Decimal
    remaining_kg: Decimal
