"""Phase 5 Verification Script:
Verifies:
1. GET /orders/{order_id} multi-seller response schema.
2. GET /orders/{order_id}/summary structured bill.
3. 409 Conflict protection on GET /orders/{order_id}/invoices.pdf before invoices ready.
4. Single-seller invoice PDF generation (GET /invoices/{invoice_id}/pdf).
5. Consolidated multi-page PDF generation (GET /orders/{order_id}/invoices.pdf) with summary cover + all seller invoices.
"""

from __future__ import annotations

import asyncio
import io
import uuid
import httpx
from pypdf import PdfReader
from sqlalchemy import text

import sys
sys.path.insert(0, "backend")

from app.database import async_session_factory
from app.consumers.invoice_consumer import handle_suborder_created
from app.main import app

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"


async def run_phase5_verification():
    print("\n" + "="*65)
    print("RUNNING PHASE 5 ORDERS & INVOICES PDF APIS VERIFICATION")
    print("="*65 + "\n")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Place a 3-seller order
        async with async_session_factory() as session:
            res = await session.execute(text("SELECT id, name FROM products LIMIT 3"))
            products = res.mappings().all()
            for p in products:
                await session.execute(
                    text("UPDATE seller_offers SET qty = 20 WHERE product_id = :p"),
                    {"p": p["id"]}
                )
            await session.commit()

        p1, p2, p3 = products[0], products[1], products[2]
        res_checkout = await client.post(
            "/checkout",
            json={
                "customer_id": CUSTOMER_ID,
                "city": "Bengaluru",
                "items": [
                    {"product_id": str(p1["id"]), "quantity": 1},
                    {"product_id": str(p2["id"]), "quantity": 1},
                    {"product_id": str(p3["id"]), "quantity": 1},
                ],
            },
        )
        assert res_checkout.status_code == 200, f"Checkout failed: {res_checkout.text}"
        data = res_checkout.json()
        order_id = data["order_id"]
        sub_orders = data["sub_orders"]
        expected_invoices = len(sub_orders)
        print(f"--> Placed Order #{order_id[:8]} with {expected_invoices} sub-orders.")

        # TEST A: 409 Conflict Protection on /invoices.pdf before invoices ready
        print("\n--> Test A: Testing 409 Conflict Protection on /orders/{id}/invoices.pdf...")
        res_pdf_early = await client.get(f"/orders/{order_id}/invoices.pdf")
        assert res_pdf_early.status_code == 409, f"Expected 409 Conflict, got {res_pdf_early.status_code}"
        print(f"    [PASS] 409 Conflict correctly returned while invoices are pending: {res_pdf_early.json()['detail']}")

        # TEST B: Process invoices for all sub-orders
        print("\n--> Test B: Processing invoices for sub-orders...")
        for so in sub_orders:
            s_id = so.get("seller_id") or so["seller"]["id"]
            await handle_suborder_created({
                "event_id": str(uuid.uuid4()),
                "event_type": "suborder.created",
                "order_id": order_id,
                "sub_order_id": so["sub_order_id"],
                "seller_id": s_id,
            })

        # TEST C: Verify GET /orders/{order_id} enriched response
        print("\n--> Test C: Testing GET /orders/{order_id}...")
        res_ord = await client.get(f"/orders/{order_id}")
        assert res_ord.status_code == 200
        ord_data = res_ord.json()
        assert ord_data["invoices_ready"] == expected_invoices
        assert ord_data["all_invoices_ready"] is True
        assert ord_data["invoices_download_url"] == f"/orders/{order_id}/invoices.pdf"
        assert len(ord_data["sub_orders"]) == expected_invoices
        for so in ord_data["sub_orders"]:
            assert so["invoice"] is not None
            assert so["invoice"]["invoice_no"].startswith("INV-")
            assert so["shipment"] is not None
            assert so["shipment"]["tracking_number"].startswith("TRK-")
        print(f"    [PASS] GET /orders/{order_id} returned all {expected_invoices} packages with full invoice & shipment tracking.")

        # TEST D: Verify GET /orders/{order_id}/summary
        print("\n--> Test D: Testing GET /orders/{order_id}/summary...")
        res_summary = await client.get(f"/orders/{order_id}/summary")
        assert res_summary.status_code == 200
        sum_data = res_summary.json()
        assert sum_data["packages_count"] == expected_invoices
        assert sum_data["all_invoices_ready"] is True
        print(f"    [PASS] GET /orders/{order_id}/summary returned consolidated bill with {len(sum_data['packages'])} packages.")

        # TEST E: Verify Individual Seller Tax Invoice PDF (GET /invoices/{id}/pdf)
        print("\n--> Test E: Testing GET /invoices/{invoice_id}/pdf...")
        first_inv_id = ord_data["sub_orders"][0]["invoice"]["id"]
        res_single_pdf = await client.get(f"/invoices/{first_inv_id}/pdf")
        assert res_single_pdf.status_code == 200
        assert res_single_pdf.headers["content-type"] == "application/pdf"
        assert res_single_pdf.content.startswith(b"%PDF")
        
        # Parse PDF to verify page count and content
        reader = PdfReader(io.BytesIO(res_single_pdf.content))
        assert len(reader.pages) >= 1
        page1_text = reader.pages[0].extract_text()
        assert "TAX INVOICE" in page1_text
        assert ord_data["sub_orders"][0]["invoice"]["invoice_no"] in page1_text
        print(f"    [PASS] Single invoice PDF valid: 1 page, verified 'TAX INVOICE' and invoice number.")

        # TEST F: Verify Consolidated Multi-Page Invoices PDF (GET /orders/{id}/invoices.pdf)
        print("\n--> Test F: Testing GET /orders/{order_id}/invoices.pdf...")
        res_all_pdf = await client.get(f"/orders/{order_id}/invoices.pdf")
        assert res_all_pdf.status_code == 200
        assert res_all_pdf.headers["content-type"] == "application/pdf"
        assert res_all_pdf.content.startswith(b"%PDF")

        # Parse merged PDF: must have 1 summary page + N seller invoice pages
        merged_reader = PdfReader(io.BytesIO(res_all_pdf.content))
        expected_pages = 1 + expected_invoices
        assert len(merged_reader.pages) == expected_pages, f"Expected {expected_pages} pages, got {len(merged_reader.pages)}"
        
        # Verify page 1 is summary
        summary_text = merged_reader.pages[0].extract_text()
        assert "ORDER CONSIGNMENT SUMMARY" in summary_text
        assert "Grand Total" in summary_text

        # Verify pages 2..N contain each seller invoice
        for p_idx in range(1, expected_pages):
            inv_text = merged_reader.pages[p_idx].extract_text()
            assert "TAX INVOICE" in inv_text

        print(f"    [PASS] Consolidated PDF verified: exactly {len(merged_reader.pages)} pages (1 Cover Summary + {expected_invoices} Seller Tax Invoices).")

    print("\n" + "="*65)
    print("ALL PHASE 5 VERIFICATIONS PASSED SUCCESSFULLY!")
    print("="*65 + "\n")
    return True


if __name__ == "__main__":
    asyncio.run(run_phase5_verification())
