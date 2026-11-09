"""Fictional demo data for local development.

Everything here is invented. Supplier and customer names, weights, rates and
costs are placeholders, never real business data.

`seed()` is idempotent: settings are ensured on every call, and the demo rows
are inserted only when the database has no purchase lots yet. Running it twice
therefore leaves the same data behind.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Alloy,
    GstMode,
    Heat,
    HeatInput,
    ItemType,
    MonthlyExpense,
    PurchaseLot,
    PurchaseTransportMode,
    ReportResult,
    Sale,
    SaleTransportMode,
    Setting,
    SpectroReport,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = ROOT / "seed_data" / "sample_spectro.pdf"

DEFAULT_GST_RATE = Decimal("0.18")
DEFAULT_PLANNED_YIELD_PCT = Decimal("89.00")


def ensure_settings(
    session: Session,
    *,
    gst_rate: Decimal = DEFAULT_GST_RATE,
    planned_yield_pct: Decimal = DEFAULT_PLANNED_YIELD_PCT,
) -> Setting:
    """Create the singleton settings row if it is missing.

    An existing row is left untouched, so a workshop can change its own rates
    without `make seed` overwriting them.
    """
    setting = session.get(Setting, 1)
    if setting is None:
        setting = Setting(
            id=1, gst_rate=gst_rate, planned_yield_pct=planned_yield_pct
        )
        session.add(setting)
        session.flush()
    return setting


def _counts(session: Session) -> dict[str, int]:
    def count(model: type) -> int:
        return session.scalar(select(func.count()).select_from(model)) or 0

    return {
        "settings": count(Setting),
        "lots": count(PurchaseLot),
        "heats": count(Heat),
        "sales": count(Sale),
        "reports": count(SpectroReport),
        "expenses": count(MonthlyExpense),
    }


def seed(session: Session) -> dict[str, int]:
    """Insert the demo data set once and return row counts per table."""
    ensure_settings(session)

    if session.scalar(select(func.count()).select_from(PurchaseLot)):
        session.commit()
        return _counts(session)

    lot_a = PurchaseLot(
        purchase_date=date(2026, 9, 28),
        supplier="Demo Scrap Traders",
        notes="Fictional demo lot A",
        weight_kg=Decimal("5000.00"),
        rate_per_kg=Decimal("152.50"),
        gst_mode=GstMode.WITHOUT,
        transport_mode=PurchaseTransportMode.WE_PAY,
        transport_cost=Decimal("4500.00"),
    )
    lot_b = PurchaseLot(
        purchase_date=date(2026, 10, 5),
        supplier="Sample Alloys (Demo)",
        notes="Fictional demo lot B",
        weight_kg=Decimal("3000.00"),
        rate_per_kg=Decimal("168.00"),
        gst_mode=GstMode.WITH,
        transport_mode=PurchaseTransportMode.SUPPLIER_DELIVERS,
        transport_cost=Decimal("0.00"),
    )
    lot_c = PurchaseLot(
        purchase_date=date(2026, 10, 12),
        supplier="Example Metal Works",
        notes="Fictional demo lot C",
        weight_kg=Decimal("1500.00"),
        rate_per_kg=Decimal("96.00"),
        gst_mode=GstMode.WITHOUT,
        transport_mode=PurchaseTransportMode.WE_PAY,
        transport_cost=Decimal("1800.00"),
    )
    session.add_all([lot_a, lot_b, lot_c])
    session.flush()

    heat_1 = Heat(
        heat_no="H-2026-001",
        heat_date=date(2026, 10, 14),
        duration_hours=Decimal("8.50"),
        alloy=Alloy.ADC12,
        output_kg=Decimal("3100.00"),
        dross_kg=Decimal("250.00"),
        iron_scrap_kg=Decimal("60.00"),
        oil_cost=Decimal("4200.00"),
        power_cost=Decimal("9800.00"),
        labour_cost=Decimal("6500.00"),
        other_cost=Decimal("1200.00"),
        notes="Fictional demo heat",
    )
    heat_2 = Heat(
        heat_no="H-2026-002",
        heat_date=date(2026, 10, 21),
        duration_hours=Decimal("6.00"),
        alloy=Alloy.ADC12,
        output_kg=Decimal("1950.00"),
        dross_kg=Decimal("170.00"),
        iron_scrap_kg=Decimal("40.00"),
        oil_cost=Decimal("2600.00"),
        power_cost=Decimal("6200.00"),
        labour_cost=Decimal("4800.00"),
        other_cost=Decimal("800.00"),
        notes="Fictional demo heat",
    )
    heat_3 = Heat(
        heat_no="H-2026-003",
        heat_date=date(2026, 10, 28),
        duration_hours=Decimal("7.25"),
        alloy=Alloy.LM6,
        output_kg=Decimal("2200.00"),
        dross_kg=Decimal("210.00"),
        iron_scrap_kg=Decimal("45.00"),
        oil_cost=Decimal("3100.00"),
        power_cost=Decimal("7100.00"),
        labour_cost=Decimal("5200.00"),
        other_cost=Decimal("900.00"),
        notes="Fictional demo heat",
    )
    session.add_all([heat_1, heat_2, heat_3])
    session.flush()

    session.add_all(
        [
            HeatInput(heat_id=heat_1.id, lot_id=lot_a.id, kg=Decimal("3000.00")),
            HeatInput(heat_id=heat_1.id, lot_id=lot_c.id, kg=Decimal("500.00")),
            HeatInput(heat_id=heat_2.id, lot_id=lot_a.id, kg=Decimal("1800.00")),
            HeatInput(heat_id=heat_2.id, lot_id=lot_c.id, kg=Decimal("400.00")),
            HeatInput(heat_id=heat_3.id, lot_id=lot_b.id, kg=Decimal("2500.00")),
        ]
    )

    session.add_all(
        [
            Sale(
                sale_date=date(2026, 10, 20),
                customer="Demo Castings",
                item_type=ItemType.ADC12,
                heat_id=heat_1.id,
                weight_kg=Decimal("1500.00"),
                rate_per_kg=Decimal("210.00"),
                gst_mode=GstMode.WITH,
                transport_mode=SaleTransportMode.CUSTOMER_ARRANGES,
                transport_cost=Decimal("0.00"),
                transport_billed=Decimal("0.00"),
            ),
            Sale(
                sale_date=date(2026, 10, 24),
                customer="Fictional Foundry",
                item_type=ItemType.ADC12,
                heat_id=heat_1.id,
                weight_kg=Decimal("1000.00"),
                rate_per_kg=Decimal("212.50"),
                gst_mode=GstMode.WITHOUT,
                transport_mode=SaleTransportMode.WE_PAY_ABSORB,
                transport_cost=Decimal("1500.00"),
                transport_billed=Decimal("0.00"),
            ),
            Sale(
                sale_date=date(2026, 10, 30),
                customer="Sample Auto Parts",
                item_type=ItemType.LM6,
                heat_id=heat_3.id,
                weight_kg=Decimal("1200.00"),
                rate_per_kg=Decimal("245.00"),
                gst_mode=GstMode.WITH,
                transport_mode=SaleTransportMode.CUSTOMER_ARRANGES,
                transport_cost=Decimal("0.00"),
                transport_billed=Decimal("0.00"),
            ),
            Sale(
                sale_date=date(2026, 10, 25),
                customer="Example Industries",
                item_type=ItemType.DROSS,
                heat_id=heat_1.id,
                weight_kg=Decimal("250.00"),
                rate_per_kg=Decimal("35.00"),
                gst_mode=GstMode.WITH,
                transport_mode=SaleTransportMode.WE_PAY_BILL,
                transport_cost=Decimal("500.00"),
                transport_billed=Decimal("700.00"),
            ),
            Sale(
                sale_date=date(2026, 10, 27),
                customer="Demo Scrap Traders",
                item_type=ItemType.IRON_SCRAP,
                heat_id=heat_2.id,
                weight_kg=Decimal("40.00"),
                rate_per_kg=Decimal("28.00"),
                gst_mode=GstMode.WITHOUT,
                transport_mode=SaleTransportMode.CUSTOMER_ARRANGES,
                transport_cost=Decimal("0.00"),
                transport_billed=Decimal("0.00"),
            ),
        ]
    )

    pdf_bytes = SAMPLE_PDF.read_bytes()
    session.add(
        SpectroReport(
            heat_id=heat_1.id,
            sample_no=1,
            file_key="seed_data/sample_spectro.pdf",
            original_filename="sample-spectro.pdf",
            size_bytes=len(pdf_bytes),
            uploaded_at=datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc),
            grade_tested="ADC12",
            result=ReportResult.PASS,
            notes="Fictional demo report",
            elements={
                "Si": "11.20",
                "Fe": "0.85",
                "Cu": "1.90",
                "Mn": "0.35",
                "Mg": "0.20",
            },
        )
    )

    session.add_all(
        [
            MonthlyExpense(
                month="2026-10", category="Rent", amount=Decimal("35000.00")
            ),
            MonthlyExpense(
                month="2026-10", category="Salaries", amount=Decimal("120000.00")
            ),
            MonthlyExpense(
                month="2026-10", category="Utilities", amount=Decimal("18000.00")
            ),
        ]
    )

    session.commit()
    return _counts(session)


def main() -> None:
    from app.db import SessionLocal

    with SessionLocal() as session:
        counts = seed(session)
    summary = ", ".join(f"{name}={value}" for name, value in counts.items())
    print(f"seed complete: {summary}")


if __name__ == "__main__":
    main()
