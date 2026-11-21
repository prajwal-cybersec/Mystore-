"""Phase 4 Verification Script:
Verifies Notification Aggregation (Rule 8):
- Never sends N notifications for 1 order.
- Waits until ALL invoices are generated (invoices_ready == invoices_expected).
- Generates exactly ONE consolidated SMS and ONE consolidated Email.
- Includes every seller's tax invoice number and shipment details.
- Idempotent against duplicate invoice events.
"""

from __future__ import annotations

import asyncio
import uuid
import httpx
from sqlalchemy import text

import sys
sys.path.insert(0, "backend")

from app.database import async_session_factory
from app.consumers.invoice_consumer import handle_suborder_created
from app.consumers.notification_consumer import handle_invoice_generated
from app.main import app

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"


async def run_phase4_verification():
    print("\n" + "="*65)
    print("RUNNING PHASE 4 NOTIFICATION AGGREGATION VERIFICATION")
    print("="*65 + "\n")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Fetch 3 products to create a 3-seller order
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
        print(f"--> Placed Order #{order_id[:8]} with {expected_invoices} packages from {expected_invoices} sellers.")

        # 2. TEST A: Process ONLY First Sub-Order (invoices_ready = 1 < 3)
        print("\n--> Test A: Partial Invoicing (1/3 invoices ready)...")
        first_so = sub_orders[0]
        seller_id = first_so.get("seller_id") or first_so["seller"]["id"]
        await handle_suborder_created({
            "event_id": str(uuid.uuid4()),
            "event_type": "suborder.created",
            "order_id": order_id,
            "sub_order_id": first_so["sub_order_id"],
            "seller_id": seller_id,
        })

        # Trigger notification consumer with first invoice
        await handle_invoice_generated({"order_id": order_id})

        # Check DB: Notification count must still be ZERO!
        async with async_session_factory() as session:
            notif_res = await session.execute(
                text("SELECT count(*) FROM notifications WHERE order_id = :oid"),
                {"oid": order_id}
            )
            count = notif_res.scalar() or 0
            assert count == 0, f"Expected 0 notifications while invoices pending, got {count}"
            print("    [PASS] Zero notifications sent while remaining invoices are pending.")

        # 3. TEST B: Complete all remaining sub-order invoices
        print("\n--> Test B: Completing remaining invoices and triggering aggregation...")
        for so in sub_orders[1:]:
            s_id = so.get("seller_id") or so["seller"]["id"]
            await handle_suborder_created({
                "event_id": str(uuid.uuid4()),
                "event_type": "suborder.created",
                "order_id": order_id,
                "sub_order_id": so["sub_order_id"],
                "seller_id": s_id,
            })
            # Call handler for each intermediate invoice
            await handle_invoice_generated({"order_id": order_id})

        # 4. TEST C: Verify exactly ONE aggregated SMS and ONE aggregated Email
        print("\n--> Test C: Verifying aggregated notifications in database...")
        async with async_session_factory() as session:
            notifs = await session.execute(
                text("SELECT channel, message FROM notifications WHERE order_id = :oid ORDER BY channel ASC"),
                {"oid": order_id}
            )
            rows = notifs.mappings().all()
            assert len(rows) == 2, f"Expected exactly 2 notifications (1 SMS, 1 EMAIL), got {len(rows)}"
            
            sms_notif = next(r for r in rows if r["channel"] == "SMS")
            email_notif = next(r for r in rows if r["channel"] == "EMAIL")

            print("\n    [Generated SMS Sample]:")
            print("    " + sms_notif["message"])
            print("\n    [Generated Email Sample]:")
            for line in email_notif["message"].split("\n")[:8]:
                print("    " + line)
            print("    ...")

            # Verify every seller's invoice number is in both messages
            inv_res = await session.execute(
                text("SELECT invoice_no FROM invoices WHERE sub_order_id IN (SELECT id FROM sub_orders WHERE order_id = :oid)"),
                {"oid": order_id}
            )
            all_invoices = [r["invoice_no"] for r in inv_res.mappings().all()]
            for inv_no in all_invoices:
                assert inv_no in sms_notif["message"], f"Invoice {inv_no} missing from SMS!"
                assert inv_no in email_notif["message"], f"Invoice {inv_no} missing from Email!"

            print(f"\n    [PASS] All {len(all_invoices)} seller invoice numbers verified in both SMS and Email.")

        # 5. TEST D: Idempotency against duplicate invoice events
        print("\n--> Test D: Testing Idempotency (re-triggering notification handler)...")
        await handle_invoice_generated({"order_id": order_id})
        async with async_session_factory() as session:
            final_count = (await session.execute(
                text("SELECT count(*) FROM notifications WHERE order_id = :oid"),
                {"oid": order_id}
            )).scalar()
            assert final_count == 2, f"Duplicate notification detected! Count: {final_count}"
            print("    [PASS] Zero duplicate notifications created on subsequent triggers.")

    print("\n" + "="*65)
    print("ALL PHASE 4 VERIFICATIONS PASSED SUCCESSFULLY!")
    print("="*65 + "\n")
    return True


if __name__ == "__main__":
    asyncio.run(run_phase4_verification())
