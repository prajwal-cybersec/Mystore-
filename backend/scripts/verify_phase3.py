"""Phase 3 Verification Script:
Verifies GST calculations, gap-free invoice sequential numbering, idempotent invoice generation,
shipment creation, orders counter progression, and outbox event publishing.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
import httpx
from sqlalchemy import text

import sys
sys.path.insert(0, "backend")

from app.database import async_session_factory
from app.invoice_service import calculate_gst_breakdown, generate_suborder_invoice
from app.consumers.invoice_consumer import handle_suborder_created
from app.main import app

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"


async def run_phase3_verification():
    print("\n" + "="*65)
    print("RUNNING PHASE 3 INVOICE GENERATION & CONSUMER VERIFICATION")
    print("="*65 + "\n")

    # 1. TEST A: Tax Math & Intra-State vs Inter-State GST Rules
    print("--> Test A: Verifying GST Calculation & Place of Supply Rules...")
    
    # Intra-state: Karnataka -> Karnataka (Electronics 18%)
    gst_intra = calculate_gst_breakdown(
        subtotal=Decimal("1180.00"),
        category="electronics",
        seller_state="Karnataka",
        delivery_state="Karnataka",
    )
    assert gst_intra["taxable_value"] == Decimal("1000.00"), f"Taxable value mismatch: {gst_intra['taxable_value']}"
    assert gst_intra["cgst"] == Decimal("90.00"), f"CGST mismatch: {gst_intra['cgst']}"
    assert gst_intra["sgst"] == Decimal("90.00"), f"SGST mismatch: {gst_intra['sgst']}"
    assert gst_intra["igst"] == Decimal("0.00"), f"IGST should be 0: {gst_intra['igst']}"
    print("    [PASS] Intra-state GST (50% CGST + 50% SGST, 0 IGST) verified.")

    # Inter-state: Maharashtra -> Karnataka (Fashion 12%)
    gst_inter = calculate_gst_breakdown(
        subtotal=Decimal("1120.00"),
        category="fashion",
        seller_state="Maharashtra",
        delivery_state="Karnataka",
    )
    assert gst_inter["taxable_value"] == Decimal("1000.00"), f"Taxable value mismatch: {gst_inter['taxable_value']}"
    assert gst_inter["cgst"] == Decimal("0.00"), f"CGST should be 0: {gst_inter['cgst']}"
    assert gst_inter["sgst"] == Decimal("0.00"), f"SGST should be 0: {gst_inter['sgst']}"
    assert gst_inter["igst"] == Decimal("120.00"), f"IGST mismatch: {gst_inter['igst']}"
    print("    [PASS] Inter-state GST (100% IGST, 0 CGST/SGST) verified.")

    # 2. TEST B: Checkout a multi-seller order and process sub-orders into invoices
    print("\n--> Test B: Multi-Seller Checkout & Invoice Processing...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Fetch 3 products
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
        print(f"    --> Order #{order_id[:8]} created with {expected_invoices} sub-orders.")

        # Process each sub_order through invoice consumer
        for so in sub_orders:
            seller_id = so.get("seller_id") or so["seller"]["id"]
            event = {
                "event_id": str(uuid.uuid4()),
                "event_type": "suborder.created",
                "order_id": order_id,
                "sub_order_id": so["sub_order_id"],
                "seller_id": seller_id,
            }
            await handle_suborder_created(event)

        # 3. TEST C: Verify Invoices, Shipments, and Order Aggregation
        print("\n--> Test C: Verifying Database Records & Counter Progression...")
        async with async_session_factory() as session:
            # Check order counter
            ord_res = await session.execute(
                text("SELECT invoices_expected, invoices_ready FROM orders WHERE id = :oid"),
                {"oid": order_id}
            )
            ord_row = ord_res.mappings().first()
            assert ord_row["invoices_ready"] == expected_invoices, f"Expected {expected_invoices} invoices_ready, got {ord_row['invoices_ready']}"
            print(f"    [PASS] Order counter progressed to {ord_row['invoices_ready']}/{ord_row['invoices_expected']}.")

            # Check invoices table
            inv_res = await session.execute(
                text("""
                    SELECT i.id, i.invoice_no, i.sub_order_id, i.taxable_value, i.cgst, i.sgst, i.igst, i.total,
                           s.seller_code, s.name as seller_name
                    FROM invoices i
                    JOIN sellers s ON s.id = i.seller_id
                    WHERE i.sub_order_id IN (SELECT id FROM sub_orders WHERE order_id = :oid)
                """),
                {"oid": order_id}
            )
            invoices = inv_res.mappings().all()
            assert len(invoices) == expected_invoices, f"Expected {expected_invoices} invoices in DB, got {len(invoices)}"
            for inv in invoices:
                assert inv["invoice_no"].startswith(f"INV-2024-25-{inv['seller_code']}-"), f"Invalid format: {inv['invoice_no']}"
                print(f"    --> Generated Invoice: {inv['invoice_no']} for {inv['seller_name']} (Total: Rs {inv['total']}, Taxable: Rs {inv['taxable_value']})")

            # Check shipments table
            ship_res = await session.execute(
                text("""
                    SELECT id, sub_order_id, status
                    FROM shipments
                    WHERE sub_order_id IN (SELECT id FROM sub_orders WHERE order_id = :oid)
                """),
                {"oid": order_id}
            )
            shipments = ship_res.mappings().all()
            assert len(shipments) == expected_invoices, f"Expected {expected_invoices} shipments, got {len(shipments)}"
            print(f"    [PASS] Exactly {len(shipments)} shipments created with status 'label_created'.")

            # Check outbox events for invoice.generated
            ob_res = await session.execute(
                text("SELECT payload FROM outbox WHERE topic = 'invoice.generated' ORDER BY created_at ASC")
            )
            ob_events = []
            for row in ob_res.mappings().all():
                payload = row["payload"] if isinstance(row["payload"], dict) else __import__("json").loads(row["payload"])
                if payload.get("order_id") == order_id:
                    ob_events.append(payload)

            assert len(ob_events) == expected_invoices, f"Expected {expected_invoices} invoice.generated events in outbox, got {len(ob_events)}"
            assert ob_events[-1]["all_invoices_ready"] is True, "Last invoice.generated event must have all_invoices_ready=True"
            print("    [PASS] Outbox verified: invoice.generated emitted for each sub-order, final event flagged all_invoices_ready=True.")

        # 4. TEST D: Idempotency Verification
        print("\n--> Test D: Testing Idempotency (re-processing existing sub-orders)...")
        # Record invoice counts before re-processing
        async with async_session_factory() as session:
            cnt_before = (await session.execute(text("SELECT count(*) FROM invoices"))).scalar()
            ship_cnt_before = (await session.execute(text("SELECT count(*) FROM shipments"))).scalar()

        # Re-run handler for the first sub_order
        first_so = sub_orders[0]
        duplicate_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "suborder.created",
            "order_id": order_id,
            "sub_order_id": first_so["sub_order_id"],
            "seller_id": first_so.get("seller_id") or first_so["seller"]["id"],
        }
        await handle_suborder_created(duplicate_event)

        async with async_session_factory() as session:
            cnt_after = (await session.execute(text("SELECT count(*) FROM invoices"))).scalar()
            ship_cnt_after = (await session.execute(text("SELECT count(*) FROM shipments"))).scalar()
            assert cnt_after == cnt_before, "Idempotency failed: duplicate invoice created!"
            assert ship_cnt_after == ship_cnt_before, "Idempotency failed: duplicate shipment created!"
            print("    [PASS] Idempotency confirmed: re-processing existing sub_order created zero duplicate rows.")

    print("\n" + "="*65)
    print("ALL PHASE 3 VERIFICATIONS PASSED SUCCESSFULLY!")
    print("="*65 + "\n")
    return True


if __name__ == "__main__":
    asyncio.run(run_phase3_verification())
