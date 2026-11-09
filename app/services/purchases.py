"""Purchase lot use cases and derived values."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.calc import gst_amount, landed_cost_per_kg, remaining_kg
from app.models import PurchaseLot
from app.repositories.purchases import PurchaseRepository
from app.repositories.settings import SettingsRepository
from app.schemas.purchases import PurchaseLotInput

DEFAULT_GST_RATE = Decimal("0.18")


class PurchaseError(Exception):
    """Base class for purchase rules that map to an HTTP error."""


class PurchaseNotFound(PurchaseError):
    pass


class PurchaseInUse(PurchaseError):
    pass


class PurchaseWeightBelowConsumed(PurchaseError):
    pass


@dataclass(frozen=True)
class PurchaseLotView:
    lot: PurchaseLot
    gst_amount: Decimal
    landed_cost_per_kg: Decimal | None
    consumed_kg: Decimal
    remaining_kg: Decimal


class PurchaseService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.purchases = PurchaseRepository(session)
        self.settings = SettingsRepository(session)

    def list(self) -> list[PurchaseLotView]:
        gst_rate = self._gst_rate()
        return [
            self._view(lot, consumed, gst_rate)
            for lot, consumed in self.purchases.list_with_consumed()
        ]

    def get(self, lot_id: int) -> PurchaseLotView:
        lot = self._get_or_raise(lot_id)
        consumed = self.purchases.consumed_kg(lot_id)
        return self._view(lot, consumed, self._gst_rate())

    def create(self, data: PurchaseLotInput) -> PurchaseLotView:
        lot = PurchaseLot(**data.model_dump())
        self.purchases.add(lot)
        self._commit()
        self.session.refresh(lot)
        return self._view(lot, Decimal("0.00"), self._gst_rate())

    def update(
        self, lot_id: int, data: PurchaseLotInput
    ) -> PurchaseLotView:
        lot = self._get_or_raise(lot_id)
        consumed = self.purchases.consumed_kg(lot_id)
        if data.weight_kg < consumed:
            raise PurchaseWeightBelowConsumed(
                f"weight_kg cannot be below the {consumed} kg "
                "already consumed by heats"
            )
        for field, value in data.model_dump().items():
            setattr(lot, field, value)
        self._commit()
        self.session.refresh(lot)
        return self._view(lot, consumed, self._gst_rate())

    def delete(self, lot_id: int) -> None:
        lot = self._get_or_raise(lot_id)
        if self.purchases.consumed_kg(lot_id) > 0:
            raise PurchaseInUse(
                "purchase lot is used by one or more heats"
            )
        self.purchases.delete(lot)
        self._commit()

    def _get_or_raise(self, lot_id: int) -> PurchaseLot:
        lot = self.purchases.get(lot_id)
        if lot is None:
            raise PurchaseNotFound("purchase lot not found")
        return lot

    def _gst_rate(self) -> Decimal:
        setting = self.settings.get()
        return setting.gst_rate if setting is not None else DEFAULT_GST_RATE

    def _view(
        self,
        lot: PurchaseLot,
        consumed: Decimal,
        gst_rate: Decimal,
    ) -> PurchaseLotView:
        return PurchaseLotView(
            lot=lot,
            gst_amount=gst_amount(
                lot.weight_kg, lot.rate_per_kg, gst_rate, lot.gst_mode
            ),
            landed_cost_per_kg=landed_cost_per_kg(
                lot.weight_kg,
                lot.rate_per_kg,
                lot.transport_cost,
                lot.transport_mode,
            ),
            consumed_kg=consumed,
            remaining_kg=remaining_kg(lot.weight_kg, consumed),
        )

    def _commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
