"""Sale request and response schemas."""

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

from app.models.enums import GstMode, ItemType, SaleTransportMode


class SaleWrite(BaseModel):
    """Payload for creating or replacing a sale.

    The `WE_PAY_BILL` billed-at-or-below-cost cap comes from issue #6's
    acceptance criteria; product-spec R6 only defines net freight. Both
    `WE_PAY_ABSORB` and `WE_PAY_BILL` also require a positive transport cost.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    sale_date: date
    customer: str = Field(min_length=1, max_length=200)
    item_type: ItemType
    heat_id: int | None = Field(default=None, gt=0)
    weight_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    rate_per_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    gst_mode: GstMode
    transport_mode: SaleTransportMode
    transport_cost: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )
    transport_billed: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )

    @field_validator("customer")
    @classmethod
    def customer_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("customer must not be blank")
        return value

    @model_validator(mode="after")
    def apply_transport_rules(self) -> SaleWrite:
        if self.transport_mode in (
            SaleTransportMode.WE_PAY_ABSORB,
            SaleTransportMode.WE_PAY_BILL,
        ) and self.transport_cost <= 0:
            raise ValueError(
                "transport_cost must be greater than 0 when the business "
                "pays transport"
            )

        if self.transport_mode == SaleTransportMode.CUSTOMER_ARRANGES:
            self.transport_cost = Decimal("0.00")
            self.transport_billed = Decimal("0.00")
        elif self.transport_mode == SaleTransportMode.WE_PAY_ABSORB:
            self.transport_billed = Decimal("0.00")
        elif self.transport_billed > self.transport_cost:
            raise ValueError(
                "transport_billed cannot exceed transport_cost for WE_PAY_BILL"
            )
        return self


class SaleRead(BaseModel):
    """A stored sale plus the values derived by `calc.py`."""

    id: int
    sale_date: date
    customer: str
    item_type: ItemType
    heat_id: int | None
    weight_kg: Decimal
    rate_per_kg: Decimal
    gst_mode: GstMode
    transport_mode: SaleTransportMode
    transport_cost: Decimal
    transport_billed: Decimal
    gst_amount: Decimal
    revenue: Decimal
    net_outbound_transport: Decimal
