"""Heat use cases, stock guard and derived values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.calc import (
    heat_profit,
    heat_scrap_cost,
    heat_variable_costs,
    is_provisional,
    landed_cost_per_kg,
    remaining_kg,
    sold_alloy_kg,
    total_input_kg,
    total_net_outbound_transport,
    total_sales_revenue,
    yield_pct,
)
from app.models import Alloy, Heat, HeatInput, PurchaseLot, ReportResult
from app.repositories.heats import HeatRepository
from app.repositories.settings import SettingsRepository
from app.schemas.heats import HeatInputPayload, HeatWrite
from app.services.sales import SaleView, build_sale_view

DEFAULT_GST_RATE = Decimal("0.18")


class HeatError(Exception):
    """Base class for heat rules that map to an HTTP error."""


class HeatNotFound(HeatError):
    pass


class HeatNoConflict(HeatError):
    pass


class HeatInUse(HeatError):
    pass


class HeatRuleError(HeatError):
    """A request that violates a heat rule; mapped to 422."""


class HeatStockError(HeatRuleError):
    pass


class HeatValidationError(HeatRuleError):
    pass


@dataclass(frozen=True)
class HeatInputView:
    lot_id: int
    kg: Decimal
    supplier: str
    purchase_date: date
    landed_cost_per_kg: Decimal | None


@dataclass(frozen=True)
class HeatView:
    heat: Heat
    inputs: list[HeatInputView]
    sales: list[SaleView]
    total_input_kg: Decimal
    sold_alloy_kg: Decimal
    yield_pct: Decimal | None
    scrap_cost: Decimal
    variable_costs: Decimal
    revenue: Decimal
    net_outbound_transport: Decimal
    heat_profit: Decimal | None
    is_provisional: bool


class HeatService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.heats = HeatRepository(session)
        self.settings = SettingsRepository(session)

    def list(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        alloy: Alloy | None = None,
        report_result: ReportResult | None = None,
        heat_no: str | None = None,
    ) -> list[HeatView]:
        return [
            self._view(heat)
            for heat in self.heats.list(
                from_date=from_date,
                to_date=to_date,
                alloy=alloy,
                report_result=report_result,
                heat_no=heat_no,
            )
        ]

    def get(self, heat_id: int) -> HeatView:
        return self._view(self._get_or_raise(heat_id))

    def create(self, data: HeatWrite) -> HeatView:
        try:
            self.heats.begin_write()
            self._ensure_heat_no_unique(data.heat_no)
            items = self._merge_inputs(data.inputs)
            self._validate_stock(
                items, data.output_kg, exclude_heat_id=None
            )
            heat = Heat(**data.model_dump(exclude={"inputs"}))
            self._apply_inputs(heat, items)
            self.heats.add(heat)
            self._commit_heat_write()
            return self._view(heat)
        except Exception:
            self.session.rollback()
            raise

    def update(self, heat_id: int, data: HeatWrite) -> HeatView:
        try:
            self.heats.begin_write()
            heat = self._get_or_raise(heat_id, for_update=True)
            self._ensure_heat_no_unique(
                data.heat_no, exclude_heat_id=heat_id
            )
            items = self._merge_inputs(data.inputs)
            self._validate_stock(
                items, data.output_kg, exclude_heat_id=heat_id
            )
            sold = sold_alloy_kg(
                (sale.weight_kg, sale.item_type) for sale in heat.sales
            )
            if data.output_kg < sold:
                raise HeatValidationError(
                    "output_kg cannot be below the alloy kg already sold"
                )
            for field, value in data.model_dump(
                exclude={"inputs"}
            ).items():
                setattr(heat, field, value)
            self._apply_inputs(heat, items)
            self._commit_heat_write()
            return self._view(heat)
        except Exception:
            self.session.rollback()
            raise

    def delete(self, heat_id: int) -> None:
        try:
            self.heats.begin_write()
            heat = self._get_or_raise(heat_id, for_update=True)
            if heat.sales:
                raise HeatInUse(
                    "heat is referenced by one or more sales"
                )
            self.heats.delete(heat)
            try:
                self.session.commit()
            except IntegrityError as error:
                self.session.rollback()
                raise HeatInUse(
                    "heat is referenced by one or more sales"
                ) from error
        except Exception:
            self.session.rollback()
            raise

    def _get_or_raise(
        self, heat_id: int, *, for_update: bool = False
    ) -> Heat:
        heat = self.heats.get(heat_id, for_update=for_update)
        if heat is None:
            raise HeatNotFound("heat not found")
        return heat

    def _ensure_heat_no_unique(
        self, heat_no: str, *, exclude_heat_id: int | None = None
    ) -> None:
        existing = self.heats.get_by_heat_no(heat_no)
        if existing is not None and existing.id != exclude_heat_id:
            raise HeatNoConflict("heat_no already exists")

    def _merge_inputs(
        self, inputs: list[HeatInputPayload]
    ) -> list[tuple[int, Decimal]]:
        """Sum repeated lot lines so the stock check sees the full draw."""
        merged: dict[int, Decimal] = {}
        for item in inputs:
            merged[item.lot_id] = (
                merged.get(item.lot_id, Decimal("0.00")) + item.kg
            )
        return list(merged.items())

    def _validate_stock(
        self,
        items: list[tuple[int, Decimal]],
        output_kg: Decimal,
        *,
        exclude_heat_id: int | None,
    ) -> None:
        lot_ids = [lot_id for lot_id, _ in items]
        lots = self.heats.get_lots(lot_ids, for_update=True)
        by_id = {lot.id: lot for lot in lots}
        missing = [lot_id for lot_id in lot_ids if lot_id not in by_id]
        if missing:
            raise HeatValidationError(
                f"unknown purchase lot: {missing[0]}"
            )

        total = total_input_kg([kg for _, kg in items])
        if total > 0 and output_kg > total:
            raise HeatValidationError(
                "output_kg cannot exceed total input kg"
            )

        consumed = self.heats.consumed_by_lots(
            lot_ids, exclude_heat_id=exclude_heat_id
        )
        for lot_id, kg in items:
            lot = by_id[lot_id]
            available = remaining_kg(
                lot.weight_kg, consumed.get(lot_id, Decimal("0.00"))
            )
            if kg > available:
                raise HeatStockError(
                    f"not enough stock in lot {lot_id}: "
                    f"requested {kg} kg, available {available} kg"
                )

    def _apply_inputs(
        self, heat: Heat, items: list[tuple[int, Decimal]]
    ) -> None:
        """Update inputs in place so re-saving the same lot cannot collide."""
        desired = dict(items)
        existing = {item.lot_id: item for item in list(heat.inputs)}

        for lot_id, item in existing.items():
            if lot_id not in desired:
                heat.inputs.remove(item)

        for lot_id, kg in desired.items():
            item = existing.get(lot_id)
            if item is None:
                heat.inputs.append(HeatInput(lot_id=lot_id, kg=kg))
            else:
                item.kg = kg

    def _view(self, heat: Heat) -> HeatView:
        inputs: list[HeatInputView] = []
        scrap_pairs: list[tuple[Decimal, Decimal]] = []

        for item in sorted(heat.inputs, key=lambda row: row.lot_id):
            lot: PurchaseLot = item.lot
            landed = landed_cost_per_kg(
                lot.weight_kg,
                lot.rate_per_kg,
                lot.transport_cost,
                lot.transport_mode,
            )
            if landed is not None:
                scrap_pairs.append((item.kg, landed))
            inputs.append(
                HeatInputView(
                    lot_id=item.lot_id,
                    kg=item.kg,
                    supplier=lot.supplier,
                    purchase_date=lot.purchase_date,
                    landed_cost_per_kg=landed,
                )
            )

        gst_rate = self._gst_rate()
        sales = [
            build_sale_view(sale, gst_rate)
            for sale in sorted(
                heat.sales, key=lambda row: (row.sale_date, row.id)
            )
        ]
        sold = sold_alloy_kg(
            (view.sale.weight_kg, view.sale.item_type) for view in sales
        )
        revenue = total_sales_revenue(
            (view.sale.weight_kg, view.sale.rate_per_kg)
            for view in sales
        )
        net_transport = total_net_outbound_transport(
            (
                view.sale.transport_mode,
                view.sale.transport_cost,
                view.sale.transport_billed,
            )
            for view in sales
        )

        total = total_input_kg([item.kg for item in heat.inputs])
        scrap = heat_scrap_cost(scrap_pairs)
        variable = heat_variable_costs(
            oil_cost=heat.oil_cost,
            power_cost=heat.power_cost,
            labour_cost=heat.labour_cost,
            other_cost=heat.other_cost,
        )
        profit = (
            heat_profit(
                revenue=revenue,
                scrap_cost=scrap,
                variable_costs=variable,
                net_transport=net_transport,
            )
            if total > 0
            else None
        )

        return HeatView(
            heat=heat,
            inputs=inputs,
            sales=sales,
            total_input_kg=total,
            sold_alloy_kg=sold,
            yield_pct=yield_pct(heat.output_kg, total),
            scrap_cost=scrap,
            variable_costs=variable,
            revenue=revenue,
            net_outbound_transport=net_transport,
            heat_profit=profit,
            is_provisional=is_provisional(sold, heat.output_kg),
        )

    def _gst_rate(self) -> Decimal:
        setting = self.settings.get()
        return setting.gst_rate if setting is not None else DEFAULT_GST_RATE

    def _commit_heat_write(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise HeatNoConflict("heat_no already exists") from error
