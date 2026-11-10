"""Heat request and response schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.models.enums import Alloy
from app.schemas.reports import ReportRead
from app.schemas.sales import SaleRead


class HeatInputPayload(BaseModel):
    """One lot reference and the kilograms taken from it."""

    model_config = ConfigDict(str_strip_whitespace=True)

    lot_id: int = Field(gt=0)
    kg: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class HeatInputRead(BaseModel):
    """A stored input plus the lot details the detail screen needs."""

    lot_id: int
    kg: Decimal
    supplier: str
    purchase_date: date
    landed_cost_per_kg: Decimal | None


class HeatWrite(BaseModel):
    """Payload for creating or replacing a heat and its input lines."""

    model_config = ConfigDict(str_strip_whitespace=True)

    heat_no: str = Field(min_length=1, max_length=50)
    heat_date: date
    duration_hours: Decimal | None = Field(
        default=None, ge=0, max_digits=6, decimal_places=2
    )
    notes: str | None = None
    alloy: Alloy
    output_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    dross_kg: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )
    iron_scrap_kg: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )
    oil_cost: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )
    power_cost: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )
    labour_cost: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )
    other_cost: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2
    )
    inputs: list[HeatInputPayload] = Field(default_factory=list)

    @field_validator("heat_no")
    @classmethod
    def heat_no_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("heat_no must not be blank")
        return value

    @field_validator("notes")
    @classmethod
    def blank_notes_become_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class HeatRead(BaseModel):
    """A heat plus the values derived by `calc.py`."""

    id: int
    heat_no: str
    heat_date: date
    duration_hours: Decimal | None
    notes: str | None
    alloy: Alloy
    output_kg: Decimal
    dross_kg: Decimal
    iron_scrap_kg: Decimal
    oil_cost: Decimal
    power_cost: Decimal
    labour_cost: Decimal
    other_cost: Decimal
    inputs: list[HeatInputRead]
    sales: list[SaleRead]
    reports: list[ReportRead]
    total_input_kg: Decimal
    sold_alloy_kg: Decimal
    yield_pct: Decimal | None
    scrap_cost: Decimal
    variable_costs: Decimal
    revenue: Decimal
    net_outbound_transport: Decimal
    heat_profit: Decimal | None
    is_provisional: bool
