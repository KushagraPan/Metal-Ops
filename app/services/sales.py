"""Sale use cases, alloy cap and derived values."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.calc import (
    gst_amount,
    net_outbound_transport,
    sale_revenue,
)
from app.models import Heat, ItemType, Sale
from app.repositories.heats import HeatRepository
from app.repositories.sales import SaleRepository
from app.repositories.settings import SettingsRepository
from app.schemas.sales import SaleWrite

DEFAULT_GST_RATE = Decimal("0.18")
ALLOY_ITEM_TYPES = {ItemType.ADC12, ItemType.LM6}


class SaleError(Exception):
    """Base class for sale rules that map to an HTTP error."""


class SaleNotFound(SaleError):
    pass


class SaleRuleError(SaleError):
    """A request that violates a sale rule; mapped to 422."""


class SaleValidationError(SaleRuleError):
    pass


@dataclass(frozen=True)
class SaleView:
    sale: Sale
    gst_amount: Decimal
    revenue: Decimal
    net_outbound_transport: Decimal


def build_sale_view(sale: Sale, gst_rate: Decimal) -> SaleView:
    """Build the derived view shared by the sales and heats APIs."""
    return SaleView(
        sale=sale,
        gst_amount=gst_amount(
            sale.weight_kg, sale.rate_per_kg, gst_rate, sale.gst_mode
        ),
        revenue=sale_revenue(sale.weight_kg, sale.rate_per_kg),
        net_outbound_transport=net_outbound_transport(
            sale.transport_mode, sale.transport_cost, sale.transport_billed
        ),
    )


class SaleService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sales = SaleRepository(session)
        self.heats = HeatRepository(session)
        self.settings = SettingsRepository(session)

    def list(self) -> list[SaleView]:
        gst_rate = self._gst_rate()
        return [
            build_sale_view(sale, gst_rate) for sale in self.sales.list()
        ]

    def get(self, sale_id: int) -> SaleView:
        return build_sale_view(
            self._get_or_raise(sale_id), self._gst_rate()
        )

    def create(self, data: SaleWrite) -> SaleView:
        try:
            self.sales.begin_write()
            heat = self._heat_for_sale(data, for_update=True)
            self._validate_alloy_cap(data, heat, sale_id=None)
            sale = Sale(**data.model_dump())
            self.sales.add(sale)
            self.session.commit()
            return build_sale_view(sale, self._gst_rate())
        except Exception:
            self.session.rollback()
            raise

    def update(self, sale_id: int, data: SaleWrite) -> SaleView:
        try:
            self.sales.begin_write()
            sale = self._get_or_raise(sale_id, for_update=True)
            heat = self._heat_for_sale(data, for_update=True)
            self._validate_alloy_cap(
                data, heat, sale_id=sale.id
            )
            for field, value in data.model_dump().items():
                setattr(sale, field, value)
            self.session.commit()
            return build_sale_view(sale, self._gst_rate())
        except Exception:
            self.session.rollback()
            raise

    def delete(self, sale_id: int) -> None:
        try:
            self.sales.begin_write()
            sale = self._get_or_raise(sale_id, for_update=True)
            self.sales.delete(sale)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _get_or_raise(
        self, sale_id: int, *, for_update: bool = False
    ) -> Sale:
        sale = self.sales.get(sale_id, for_update=for_update)
        if sale is None:
            raise SaleNotFound("sale not found")
        return sale

    def _heat_for_sale(
        self, data: SaleWrite, *, for_update: bool
    ) -> Heat | None:
        heat: Heat | None = None
        if data.heat_id is not None:
            heat = self.heats.get(data.heat_id, for_update=for_update)
            if heat is None:
                raise SaleValidationError("heat not found")

        if data.item_type in ALLOY_ITEM_TYPES:
            if heat is None:
                raise SaleValidationError(
                    "alloy sales require a linked heat"
                )
            if heat.alloy.value != data.item_type.value:
                raise SaleValidationError(
                    "sale item type must match the heat alloy"
                )
        return heat

    def _validate_alloy_cap(
        self, data: SaleWrite, heat: Heat | None, *, sale_id: int | None
    ) -> None:
        if data.item_type not in ALLOY_ITEM_TYPES or heat is None:
            return
        sold = self.sales.sold_alloy_kg(
            heat.id, exclude_sale_id=sale_id
        )
        if sold + data.weight_kg > heat.output_kg:
            raise SaleValidationError(
                "total alloy kg sold cannot exceed heat output_kg"
            )

    def _gst_rate(self) -> Decimal:
        setting = self.settings.get()
        return setting.gst_rate if setting is not None else DEFAULT_GST_RATE
