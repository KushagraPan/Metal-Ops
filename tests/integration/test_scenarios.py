"""End-to-end acceptance scenarios from product-spec.md against PostgreSQL.

Scenarios from section 8:
1. Profit (worked example): yield 89.0% and profit 3,160.00, then 5,160.00 after switching
   the sale to WE_PAY_BILL with 2,000 billed.
2. Report history: heat with two uploaded PDFs; searching heat number opens both reports.
3. Stock guard: lot with 500 kg remaining; trying to take 600 kg is rejected (422) and
   nothing is saved.
"""

from __future__ import annotations

import io
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.integration


def test_scenario_1_profit_worked_example(auth_client: TestClient) -> None:
    """Scenario 1: Worked example in section 5.

    - Lot: 1,000 kg at 200.00/kg, WITH GST, WE_PAY transport 2,000.00 (landed 202.00/kg)
    - Heat: takes 1,000 kg, output 890 kg ADC12, dross 60 kg, iron scrap 5 kg. Costs: 11,000
    - Sales: ADC12 890 kg @ 240.00, WE_PAY_ABSORB 3,000; Dross 60 kg @ 90.00; Iron 5 kg @ 32.00
    - Yield: 89.0%, Profit: 3,160.00
    - Switch sale to WE_PAY_BILL with 2,000 billed: Profit: 5,160.00
    """
    # 1. Create Purchase Lot
    lot_payload = {
        "purchase_date": "2026-10-01",
        "supplier": "Apex Scrap Traders",
        "weight_kg": 1000.00,
        "rate_per_kg": 200.00,
        "gst_mode": "WITH",
        "transport_mode": "WE_PAY",
        "transport_cost": 2000.00,
        "notes": "Spec section 5 test lot",
    }
    lot_res = auth_client.post("/api/purchases", json=lot_payload)
    assert lot_res.status_code == 201, lot_res.text
    lot = lot_res.json()
    lot_id = lot["id"]
    assert lot["landed_cost_per_kg"] == 202.00 or lot["landed_cost_per_kg"] == "202.00"

    # 2. Create Heat
    heat_payload = {
        "heat_no": "H-2026-001",
        "heat_date": "2026-10-05",
        "duration_hours": 4.5,
        "alloy": "ADC12",
        "output_kg": 890.00,
        "dross_kg": 60.00,
        "iron_scrap_kg": 5.00,
        "oil_cost": 6000.00,
        "power_cost": 3000.00,
        "labour_cost": 2000.00,
        "other_cost": 0.00,
        "inputs": [{"lot_id": lot_id, "kg": 1000.00}],
        "notes": "Spec worked example heat",
    }
    heat_res = auth_client.post("/api/heats", json=heat_payload)
    assert heat_res.status_code == 201, heat_res.text
    heat = heat_res.json()
    heat_id = heat["id"]

    # 3. Create Sales
    # 3a. ADC12 sale
    sale_adc12_payload = {
        "sale_date": "2026-10-10",
        "customer": "Zenith Foundry",
        "item_type": "ADC12",
        "heat_id": heat_id,
        "weight_kg": 890.00,
        "rate_per_kg": 240.00,
        "gst_mode": "WITH",
        "transport_mode": "WE_PAY_ABSORB",
        "transport_cost": 3000.00,
        "transport_billed": 0.00,
    }
    sale1_res = auth_client.post("/api/sales", json=sale_adc12_payload)
    assert sale1_res.status_code == 201, sale1_res.text
    sale_adc12_id = sale1_res.json()["id"]

    # 3b. Dross sale
    sale_dross_payload = {
        "sale_date": "2026-10-10",
        "customer": "Bharat Byproducts",
        "item_type": "DROSS",
        "heat_id": heat_id,
        "weight_kg": 60.00,
        "rate_per_kg": 90.00,
        "gst_mode": "WITH",
        "transport_mode": "CUSTOMER_ARRANGES",
        "transport_cost": 0.00,
        "transport_billed": 0.00,
    }
    sale2_res = auth_client.post("/api/sales", json=sale_dross_payload)
    assert sale2_res.status_code == 201, sale2_res.text

    # 3c. Iron scrap sale
    sale_iron_payload = {
        "sale_date": "2026-10-10",
        "customer": "City Scrap",
        "item_type": "IRON_SCRAP",
        "heat_id": heat_id,
        "weight_kg": 5.00,
        "rate_per_kg": 32.00,
        "gst_mode": "WITH",
        "transport_mode": "CUSTOMER_ARRANGES",
        "transport_cost": 0.00,
        "transport_billed": 0.00,
    }
    sale3_res = auth_client.post("/api/sales", json=sale_iron_payload)
    assert sale3_res.status_code == 201, sale3_res.text

    # 4. Verify heat detail: yield 89.0% and profit 3,160.00
    detail_res = auth_client.get(f"/api/heats/{heat_id}")
    assert detail_res.status_code == 200, detail_res.text
    detail = detail_res.json()
    assert float(detail["yield_pct"]) == 89.0
    assert float(detail["heat_profit"]) == 3160.00
    assert detail["is_provisional"] is False

    # 5. Switch ADC12 sale to WE_PAY_BILL with 2,000 billed
    update_sale_payload = {
        "sale_date": "2026-10-10",
        "customer": "Zenith Foundry",
        "item_type": "ADC12",
        "heat_id": heat_id,
        "weight_kg": 890.00,
        "rate_per_kg": 240.00,
        "gst_mode": "WITH",
        "transport_mode": "WE_PAY_BILL",
        "transport_cost": 3000.00,
        "transport_billed": 2000.00,
    }
    update_res = auth_client.put(f"/api/sales/{sale_adc12_id}", json=update_sale_payload)
    assert update_res.status_code == 200, update_res.text

    # 6. Verify heat detail shows profit 5,160.00
    detail_updated_res = auth_client.get(f"/api/heats/{heat_id}")
    assert detail_updated_res.status_code == 200, detail_updated_res.text
    detail_updated = detail_updated_res.json()
    assert float(detail_updated["yield_pct"]) == 89.0
    assert float(detail_updated["heat_profit"]) == 5160.00


def test_scenario_2_report_history(auth_client: TestClient) -> None:
    """Scenario 2: Heat with two uploaded PDFs.

    When the user searches its heat number a month later, both reports open from
    the heat detail.
    """
    # 1. Create a lot and heat dated 1 month ago
    lot_res = auth_client.post(
        "/api/purchases",
        json={
            "purchase_date": "2026-09-01",
            "supplier": "Past Supplier",
            "weight_kg": 500.00,
            "rate_per_kg": 180.00,
            "gst_mode": "WITHOUT",
            "transport_mode": "SUPPLIER_DELIVERS",
            "transport_cost": 0.00,
        },
    )
    assert lot_res.status_code == 201, lot_res.text
    lot_id = lot_res.json()["id"]

    heat_res = auth_client.post(
        "/api/heats",
        json={
            "heat_no": "H-HIST-042",
            "heat_date": "2026-09-02",
            "duration_hours": 3.0,
            "alloy": "LM6",
            "output_kg": 440.00,
            "dross_kg": 30.00,
            "iron_scrap_kg": 2.00,
            "oil_cost": 3000.00,
            "power_cost": 1500.00,
            "labour_cost": 1000.00,
            "other_cost": 0.00,
            "inputs": [{"lot_id": lot_id, "kg": 500.00}],
        },
    )
    assert heat_res.status_code == 201, heat_res.text
    heat_id = heat_res.json()["id"]

    # 2. Upload first spectro report PDF
    pdf1_content = b"%PDF-1.4\n1 0 obj\n<< /Title (First Lab Spectro Report) >>\nendobj\ntrailer\n<<>>\n%%EOF"
    upload1 = auth_client.post(
        f"/api/heats/{heat_id}/reports",
        data={"sample_no": "SAMPLE-A", "result": "PASS", "notes": "Initial melt sample"},
        files={"file": ("report_sample_a.pdf", io.BytesIO(pdf1_content), "application/pdf")},
    )
    assert upload1.status_code == 201, upload1.text
    report1_id = upload1.json()["id"]

    # 3. Upload second spectro report PDF
    pdf2_content = b"%PDF-1.4\n2 0 obj\n<< /Title (Second Lab Spectro Report) >>\nendobj\ntrailer\n<<>>\n%%EOF"
    upload2 = auth_client.post(
        f"/api/heats/{heat_id}/reports",
        data={"sample_no": "SAMPLE-B", "result": "PENDING", "notes": "Final ingot sample"},
        files={"file": ("report_sample_b.pdf", io.BytesIO(pdf2_content), "application/pdf")},
    )
    assert upload2.status_code == 201, upload2.text
    report2_id = upload2.json()["id"]

    # 4. Search heat number a month later (case-insensitive query: 'h-hist-042')
    search_res = auth_client.get("/api/heats?heat_no=h-hist-042")
    assert search_res.status_code == 200, search_res.text
    search_results = search_res.json()
    assert any(h["heat_no"] == "H-HIST-042" for h in search_results)

    # 5. Open heat detail and verify both reports are present
    detail_res = auth_client.get(f"/api/heats/{heat_id}")
    assert detail_res.status_code == 200, detail_res.text
    detail = detail_res.json()
    assert len(detail["reports"]) == 2
    report_ids = {r["id"] for r in detail["reports"]}
    assert report1_id in report_ids
    assert report2_id in report_ids

    # 6. Verify both reports download with exact bytes
    down1 = auth_client.get(f"/api/reports/{report1_id}/download")
    assert down1.status_code == 200
    assert down1.headers["content-type"] == "application/pdf"
    assert down1.content == pdf1_content

    down2 = auth_client.get(f"/api/reports/{report2_id}/download")
    assert down2.status_code == 200
    assert down2.headers["content-type"] == "application/pdf"
    assert down2.content == pdf2_content


def test_scenario_3_stock_guard(auth_client: TestClient) -> None:
    """Scenario 3: Stock guard.

    Given a lot with 500 kg remaining, when a heat tries to take 600 kg from it,
    then the request is rejected and nothing is saved.
    """
    # 1. Create lot with 500 kg
    lot_res = auth_client.post(
        "/api/purchases",
        json={
            "purchase_date": "2026-10-15",
            "supplier": "Guard Supplier",
            "weight_kg": 500.00,
            "rate_per_kg": 190.00,
            "gst_mode": "WITH",
            "transport_mode": "SUPPLIER_DELIVERS",
            "transport_cost": 0.00,
        },
    )
    assert lot_res.status_code == 201, lot_res.text
    lot_id = lot_res.json()["id"]

    # 2. Try to create heat taking 600 kg from this lot
    overdraw_payload = {
        "heat_no": "H-OVERDRAW-001",
        "heat_date": "2026-10-16",
        "duration_hours": 3.0,
        "alloy": "ADC12",
        "output_kg": 450.00,
        "dross_kg": 20.00,
        "iron_scrap_kg": 2.00,
        "oil_cost": 1000.00,
        "power_cost": 500.00,
        "labour_cost": 500.00,
        "other_cost": 0.00,
        "inputs": [{"lot_id": lot_id, "kg": 600.00}],
    }
    reject_res = auth_client.post("/api/heats", json=overdraw_payload)
    assert reject_res.status_code == 422, reject_res.text
    assert "not enough stock" in reject_res.text.lower() or "stock" in reject_res.text.lower()

    # 3. Assert nothing is saved
    heats_res = auth_client.get("/api/heats?heat_no=H-OVERDRAW-001")
    assert heats_res.status_code == 200
    assert len(heats_res.json()) == 0

    lot_check = auth_client.get(f"/api/purchases/{lot_id}")
    assert lot_check.status_code == 200
    assert float(lot_check.json()["remaining_kg"]) == 500.00

