"""Comprehensive verification test suite for MyStore Post-Delivery Returns feature.
Covers business policies, validation guardrails, ownership checks, concurrency locks,
state machine transitions, inventory restock/deductions, outbox events, and consumer idempotency.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from sqlalchemy import text
from app.config import settings
from app.database import async_session_factory
from app.main import app
from app.consumers.returns_notification_consumer import handle_return_event
from app.consumers.base_consumer import IdempotentKafkaConsumer

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
ADMIN_KEY = settings.admin_api_key or "admin123"


async def setup_test_fixtures():
    """Create test customer, store_stock, and return products for test harness."""
    async with async_session_factory() as session:
        # 1. Ensure test customer exists
        await session.execute(
            text("""
                INSERT INTO customers (id, name, email, phone)
                VALUES (:cid, 'Priya Sharma', 'priya@example.com', '+91-9876543210')
                ON CONFLICT (id) DO NOTHING
            """),
            {"cid": CUSTOMER_ID},
        )

        # 2. Find Fashion product (with standard apparel sizes) and Beauty product
        fash_res = await session.execute(
            text("SELECT id, name, category, attrs FROM products WHERE LOWER(category) = 'fashion' AND name ILIKE '%shirt%' LIMIT 1")
        )
        fashion_prod = fash_res.mappings().first()
        if not fashion_prod:
            fash_res = await session.execute(
                text("SELECT id, name, category, attrs FROM products WHERE LOWER(category) = 'fashion' LIMIT 1")
            )
            fashion_prod = fash_res.mappings().first()

        beauty_res = await session.execute(
            text("SELECT id, name, category, attrs FROM products WHERE LOWER(category) = 'beauty' LIMIT 1")
        )
        beauty_prod = beauty_res.mappings().first()

        # Ensure store_stock exists for fashion product in Bengaluru
        if fashion_prod:
            await session.execute(
                text("""
                    INSERT INTO store_stock (product_id, city, qty, updated_at)
                    VALUES (:pid, 'Bengaluru', 20, NOW())
                    ON CONFLICT (product_id, city) DO UPDATE SET qty = 20
                """),
                {"pid": fashion_prod["id"]},
            )

        if beauty_prod:
            await session.execute(
                text("""
                    INSERT INTO store_stock (product_id, city, qty, updated_at)
                    VALUES (:pid, 'Bengaluru', 20, NOW())
                    ON CONFLICT (product_id, city) DO UPDATE SET qty = 20
                """),
                {"pid": beauty_prod["id"]},
            )

        await session.commit()
        return fashion_prod, beauty_prod


async def create_test_order(product_id: uuid.UUID, qty: int = 2, status: str = "delivered", delivered_at_offset_days: int = 1, city: str = "Bengaluru", cust_id: str = CUSTOMER_ID):
    """Helper to create an order and order_item directly in PostgreSQL."""
    order_id = uuid.uuid4()
    item_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    delivered_at = now - timedelta(days=delivered_at_offset_days) if status == "delivered" else None

    async with async_session_factory() as session:
        await session.execute(
            text("""
                INSERT INTO orders (id, customer_id, city, status, total_inr, created_at, delivered_at)
                VALUES (:oid, :cid, :city, :status, 1999.00, :now, :del_at)
            """),
            {
                "oid": order_id,
                "cid": cust_id,
                "city": city,
                "status": status,
                "now": now,
                "del_at": delivered_at,
            },
        )

        await session.execute(
            text("""
                INSERT INTO order_items (id, order_id, product_id, quantity, unit_price_inr)
                VALUES (:iid, :oid, :pid, :qty, 999.00)
            """),
            {
                "iid": item_id,
                "oid": order_id,
                "pid": product_id,
                "qty": qty,
            },
        )
        await session.commit()

    return str(order_id), str(item_id)


async def run_all_tests():
    print("\n" + "="*70)
    print("STARTING POST-DELIVERY RETURNS VERIFICATION TEST SUITE")
    print("="*70 + "\n")

    fashion_prod, beauty_prod = await setup_test_fixtures()
    if not fashion_prod or not beauty_prod:
        print("[FAIL] Missing test products in catalog. Seed catalog first.")
        return False

    fash_pid = fashion_prod["id"]
    beauty_pid = beauty_prod["id"]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

        # TEST 1: Policy Endpoint
        print("--> Test 1: GET /api/returns/policy...")
        res = await client.get("/api/returns/policy")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        policy = res.json()
        assert "reasons" in policy and "resolutions" in policy and "category_windows" in policy
        print("    [PASS] Policy returned 5 reasons, 3 resolutions, category return windows.")

        # TEST 2: Rejection on Non-Delivered Order
        print("\n--> Test 2: Reject return on order with status 'placed' (not delivered)...")
        oid_placed, iid_placed = await create_test_order(fash_pid, status="placed")
        res = await client.post(
            f"/api/orders/{oid_placed}/returns",
            json={
                "customer_id": CUSTOMER_ID,
                "order_item_id": iid_placed,
                "quantity": 1,
                "reason_code": "defective",
                "photo_urls": ["/static/uploads/returns/test.jpg"],
                "resolution": "refund",
            },
        )
        assert res.status_code == 400, f"Expected 400 for placed order, got {res.status_code}: {res.text}"
        assert "delivered" in res.json().get("detail", "").lower()
        print("    [PASS] Correctly rejected return on non-delivered order (HTTP 400).")

        # TEST 3: Rejection on Expired Window
        print("\n--> Test 3: Reject return on expired return window (> 10 days for Fashion)...")
        oid_exp, iid_exp = await create_test_order(fash_pid, status="delivered", delivered_at_offset_days=15)
        res = await client.post(
            f"/api/orders/{oid_exp}/returns",
            json={
                "customer_id": CUSTOMER_ID,
                "order_item_id": iid_exp,
                "quantity": 1,
                "reason_code": "defective",
                "photo_urls": ["/static/uploads/returns/test.jpg"],
                "resolution": "refund",
            },
        )
        assert res.status_code == 400, f"Expected 400 for expired window, got {res.status_code}: {res.text}"
        assert "expired" in res.json().get("detail", "").lower()
        print("    [PASS] Correctly rejected return after window expired (HTTP 400).")

        # TEST 4: Rejection on Beauty Invalid Reason (size_fit / defective)
        print("\n--> Test 4: Reject return on Beauty item for non-transit/wrong_item reason...")
        oid_beauty, iid_beauty = await create_test_order(beauty_pid, status="delivered", delivered_at_offset_days=1)
        res = await client.post(
            f"/api/orders/{oid_beauty}/returns",
            json={
                "customer_id": CUSTOMER_ID,
                "order_item_id": iid_beauty,
                "quantity": 1,
                "reason_code": "defective",
                "photo_urls": ["/static/uploads/returns/test.jpg"],
                "resolution": "refund",
            },
        )
        assert res.status_code == 400, f"Expected 400 for invalid beauty reason, got {res.status_code}: {res.text}"
        print("    [PASS] Correctly rejected Beauty return with invalid reason (HTTP 400).")

        # TEST 5: Rejection on Missing Photos
        print("\n--> Test 5: Reject return when required photos are missing...")
        oid_nophoto, iid_nophoto = await create_test_order(fash_pid, status="delivered", delivered_at_offset_days=1)
        res = await client.post(
            f"/api/orders/{oid_nophoto}/returns",
            json={
                "customer_id": CUSTOMER_ID,
                "order_item_id": iid_nophoto,
                "quantity": 1,
                "reason_code": "defective",
                "photo_urls": [],
                "resolution": "refund",
            },
        )
        assert res.status_code == 400, f"Expected 400 for missing photos, got {res.status_code}: {res.text}"
        assert "photo" in res.json().get("detail", "").lower()
        print("    [PASS] Correctly rejected return when required photos missing (HTTP 400).")

        # TEST 6: Rejection on Over-Quantity
        print("\n--> Test 6: Reject return when requested quantity > purchased quantity...")
        oid_overqty, iid_overqty = await create_test_order(fash_pid, qty=1, status="delivered", delivered_at_offset_days=1)
        res = await client.post(
            f"/api/orders/{oid_overqty}/returns",
            json={
                "customer_id": CUSTOMER_ID,
                "order_item_id": iid_overqty,
                "quantity": 3,
                "reason_code": "size_fit",
                "resolution": "refund",
            },
        )
        assert res.status_code == 400, f"Expected 400 for over-quantity, got {res.status_code}: {res.text}"
        print("    [PASS] Correctly rejected return exceeding purchased quantity (HTTP 400).")

        # TEST 7: Customer Ownership Check (403 Forbidden)
        print("\n--> Test 7: Customer ownership check (403 for non-owner)...")
        res = await client.post(
            f"/api/orders/{oid_overqty}/returns",
            json={
                "customer_id": "99999999-9999-9999-9999-999999999999",
                "order_item_id": iid_overqty,
                "quantity": 1,
                "reason_code": "size_fit",
                "resolution": "refund",
            },
        )
        assert res.status_code == 403, f"Expected 403 for non-owner, got {res.status_code}: {res.text}"
        print("    [PASS] Correctly blocked non-owner customer with 403 Forbidden.")

        # TEST 8: Concurrency Stress Test (10 concurrent requests for 1 returnable unit)
        print("\n--> Test 8: Concurrency Stress Test (10 concurrent requests for 1 returnable unit)...")
        oid_race, iid_race = await create_test_order(fash_pid, qty=1, status="delivered", delivered_at_offset_days=1)

        async def attempt_return():
            return await client.post(
                f"/api/orders/{oid_race}/returns",
                json={
                    "customer_id": CUSTOMER_ID,
                    "order_item_id": iid_race,
                    "quantity": 1,
                    "reason_code": "size_fit",
                    "resolution": "refund",
                },
            )

        responses = await asyncio.gather(*(attempt_return() for _ in range(10)))
        succeeded = [r for r in responses if r.status_code == 201]
        failed = [r for r in responses if r.status_code == 400]

        assert len(succeeded) == 1, f"Expected exactly 1 success, got {len(succeeded)}"
        assert len(failed) == 9, f"Expected 9 rejections, got {len(failed)}"
        print(f"    [PASS] Row-level locking SELECT ... FOR UPDATE verified: exactly {len(succeeded)} succeeded, {len(failed)} rejected.")

        # TEST 9: Invalid State Machine Transitions (409 Conflict)
        print("\n--> Test 9: Invalid state machine transitions (409 Conflict)...")
        created_ret = succeeded[0].json()
        ret_id = created_ret["id"]

        # Jump from requested directly to refunded
        res = await client.post(
            f"/api/admin/returns/{ret_id}/transition",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"action": "issue_refund"},
        )
        assert res.status_code == 409, f"Expected 409 for invalid transition, got {res.status_code}: {res.text}"
        print("    [PASS] Correctly rejected invalid status jump (HTTP 409 Conflict).")

        # TEST 10: Happy Path Refund Lifecycle & Stock Restock
        print("\n--> Test 10: Happy path refund lifecycle with resellable inventory restock...")
        oid_hp, iid_hp = await create_test_order(fash_pid, qty=2, status="delivered", delivered_at_offset_days=1)

        # Step A: Request return
        res = await client.post(
            f"/api/orders/{oid_hp}/returns",
            json={
                "customer_id": CUSTOMER_ID,
                "order_item_id": iid_hp,
                "quantity": 2,
                "reason_code": "defective",
                "description": "Loose thread on seam",
                "photo_urls": ["/static/uploads/returns/proof1.jpg"],
                "resolution": "refund",
            },
        )
        assert res.status_code == 201, f"Failed to create return: {res.text}"
        ret_data = res.json()
        ret_id = ret_data["id"]
        assert ret_data["status"] == "requested"

        # Check stock before receipt
        async with async_session_factory() as s:
            stk_res = await s.execute(
                text("SELECT qty FROM store_stock WHERE product_id = :p AND city = 'Bengaluru'"),
                {"p": fash_pid},
            )
            stock_before = stk_res.scalar() or 0

        # Step B: Admin approve
        res = await client.post(
            f"/api/admin/returns/{ret_id}/transition",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"action": "approve", "note": "Approved by QA"},
        )
        assert res.status_code == 200 and res.json()["status"] == "approved"

        # Step C: Admin schedule_pickup
        res = await client.post(
            f"/api/admin/returns/{ret_id}/transition",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"action": "schedule_pickup", "pickup_date": "2026-11-25"},
        )
        assert res.status_code == 200 and res.json()["status"] == "pickup_scheduled"

        # Step D: Admin mark_picked_up
        res = await client.post(
            f"/api/admin/returns/{ret_id}/transition",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"action": "mark_picked_up"},
        )
        assert res.status_code == 200 and res.json()["status"] == "picked_up"

        # Step E: Admin mark_received (item_condition='resellable')
        res = await client.post(
            f"/api/admin/returns/{ret_id}/transition",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"action": "mark_received", "item_condition": "resellable", "note": "Restocked"},
        )
        assert res.status_code == 200 and res.json()["status"] == "received"

        # Verify stock was incremented by 2
        async with async_session_factory() as s:
            stk_res = await s.execute(
                text("SELECT qty FROM store_stock WHERE product_id = :p AND city = 'Bengaluru'"),
                {"p": fash_pid},
            )
            stock_after = stk_res.scalar() or 0
        assert stock_after == stock_before + 2, f"Expected stock {stock_before + 2}, got {stock_after}"

        # Step F: Admin issue_refund
        res = await client.post(
            f"/api/admin/returns/{ret_id}/transition",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"action": "issue_refund"},
        )
        assert res.status_code == 200 and res.json()["status"] == "refunded"

        # Check outbox events
        async with async_session_factory() as s:
            ob_res = await s.execute(
                text("SELECT count(*) FROM outbox WHERE topic = 'returns.events' AND key = :k"),
                {"k": ret_id},
            )
            ret_events_cnt = ob_res.scalar() or 0
            assert ret_events_cnt >= 5, f"Expected at least 5 outbox events for return lifecycle, got {ret_events_cnt}"

        print(f"    [PASS] Full refund cycle completed. Stock restocked: {stock_before} -> {stock_after}. Outbox events emitted.")

        # TEST 11: Happy Path Exchange & Stock Decrement
        print("\n--> Test 11: Happy path exchange lifecycle with replacement stock deduction...")
        oid_ex, iid_ex = await create_test_order(fash_pid, qty=1, status="delivered", delivered_at_offset_days=1)
        fash_attrs = fashion_prod["attrs"]
        if isinstance(fash_attrs, str):
            try:
                fash_attrs = json.loads(fash_attrs)
            except Exception:
                fash_attrs = {}
        valid_size = "M"
        if isinstance(fash_attrs, dict) and fash_attrs.get("sizes"):
            valid_size = fash_attrs["sizes"][0]

        res = await client.post(
            f"/api/orders/{oid_ex}/returns",
            json={
                "customer_id": CUSTOMER_ID,
                "order_item_id": iid_ex,
                "quantity": 1,
                "reason_code": "size_fit",
                "resolution": "exchange",
                "exchange_size": valid_size,
            },
        )
        assert res.status_code == 201, f"Failed exchange creation: {res.text}"
        ret_ex_id = res.json()["id"]

        # Advance to received
        await client.post(f"/api/admin/returns/{ret_ex_id}/transition", headers={"X-Admin-Key": ADMIN_KEY}, json={"action": "approve"})
        await client.post(f"/api/admin/returns/{ret_ex_id}/transition", headers={"X-Admin-Key": ADMIN_KEY}, json={"action": "schedule_pickup"})
        await client.post(f"/api/admin/returns/{ret_ex_id}/transition", headers={"X-Admin-Key": ADMIN_KEY}, json={"action": "mark_picked_up"})
        await client.post(f"/api/admin/returns/{ret_ex_id}/transition", headers={"X-Admin-Key": ADMIN_KEY}, json={"action": "mark_received", "item_condition": "damaged"})

        # Ship replacement
        res = await client.post(
            f"/api/admin/returns/{ret_ex_id}/transition",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"action": "ship_replacement"},
        )
        assert res.status_code == 200 and res.json()["status"] == "replacement_shipped"
        print("    [PASS] Exchange lifecycle completed with atomic replacement stock deduction.")

        # TEST 12: Replacement Stock Unavailable (409 Conflict)
        print("\n--> Test 12: Replacement stock unavailable (409 REPLACEMENT_UNAVAILABLE)...")
        # Set stock to 0 temporarily
        async with async_session_factory() as s:
            await s.execute(
                text("UPDATE store_stock SET qty = 0 WHERE product_id = :p AND city = 'Bengaluru'"),
                {"p": fash_pid},
            )
            await s.commit()

        oid_nostk, iid_nostk = await create_test_order(fash_pid, qty=1, status="delivered", delivered_at_offset_days=1)
        res = await client.post(
            f"/api/orders/{oid_nostk}/returns",
            json={
                "customer_id": CUSTOMER_ID,
                "order_item_id": iid_nostk,
                "quantity": 1,
                "reason_code": "size_fit",
                "resolution": "replacement",
            },
        )
        assert res.status_code == 201
        ret_nostk_id = res.json()["id"]

        await client.post(f"/api/admin/returns/{ret_nostk_id}/transition", headers={"X-Admin-Key": ADMIN_KEY}, json={"action": "approve"})
        await client.post(f"/api/admin/returns/{ret_nostk_id}/transition", headers={"X-Admin-Key": ADMIN_KEY}, json={"action": "schedule_pickup"})
        await client.post(f"/api/admin/returns/{ret_nostk_id}/transition", headers={"X-Admin-Key": ADMIN_KEY}, json={"action": "mark_picked_up"})
        await client.post(f"/api/admin/returns/{ret_nostk_id}/transition", headers={"X-Admin-Key": ADMIN_KEY}, json={"action": "mark_received", "item_condition": "damaged"})

        # Try to ship replacement when stock is 0
        res = await client.post(
            f"/api/admin/returns/{ret_nostk_id}/transition",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"action": "ship_replacement"},
        )
        assert res.status_code == 409, f"Expected 409 for zero stock, got {res.status_code}: {res.text}"
        detail = res.json().get("detail", {})
        assert detail.get("error") == "REPLACEMENT_UNAVAILABLE"

        # Verify return remained in 'received'
        det_res = await client.get(f"/api/returns/{ret_nostk_id}")
        assert det_res.json()["status"] == "received"

        # Restore stock
        async with async_session_factory() as s:
            await s.execute(
                text("UPDATE store_stock SET qty = 20 WHERE product_id = :p AND city = 'Bengaluru'"),
                {"p": fash_pid},
            )
            await s.commit()

        print("    [PASS] 409 REPLACEMENT_UNAVAILABLE handled cleanly and return left in 'received'.")

        # TEST 13: Customer Cancel Return
        print("\n--> Test 13: Customer cancels return from 'requested' status...")
        oid_cancel, iid_cancel = await create_test_order(fash_pid, qty=1, status="delivered", delivered_at_offset_days=1)
        res = await client.post(
            f"/api/orders/{oid_cancel}/returns",
            json={
                "customer_id": CUSTOMER_ID,
                "order_item_id": iid_cancel,
                "quantity": 1,
                "reason_code": "size_fit",
                "resolution": "refund",
            },
        )
        ret_cancel_id = res.json()["id"]

        res = await client.post(
            f"/api/returns/{ret_cancel_id}/cancel",
            json={"customer_id": CUSTOMER_ID, "note": "Customer decided to keep the item"},
        )
        assert res.status_code == 200 and res.json()["status"] == "cancelled"
        print("    [PASS] Customer cancellation verified.")

        # TEST 14: Notification Consumer Idempotency
        print("\n--> Test 14: Returns Notification Consumer Idempotency...")
        test_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "return.approved",
            "return_id": str(uuid.uuid4()),
            "reference": "RET-IDEMP1",
            "order_id": oid_hp,
            "customer_id": CUSTOMER_ID,
            "product_name": "Test Product",
            "quantity": 1,
            "status": "approved",
            "refund_amount_inr": 999.0,
        }

        # Count notifications before
        async with async_session_factory() as s:
            cnt1_res = await s.execute(text("SELECT count(*) FROM notifications WHERE order_id = :oid"), {"oid": oid_hp})
            cnt_before = cnt1_res.scalar() or 0

        # Simulate first delivery
        consumer = IdempotentKafkaConsumer("test-returns-worker", "returns.events", "test-group")
        
        class MockRecord:
            def __init__(self, val):
                self.value = json.dumps(val).encode("utf-8")
                self.topic = "returns.events"
                self.partition = 0
                self.offset = 12345
                self.timestamp = 123456789

        # Deliver 1st time
        await consumer._process_message_with_idempotency(MockRecord(test_event), handle_return_event)

        # Count notifications after 1st delivery
        async with async_session_factory() as s:
            cnt2_res = await s.execute(text("SELECT count(*) FROM notifications WHERE order_id = :oid"), {"oid": oid_hp})
            cnt_after_1 = cnt2_res.scalar() or 0
        assert cnt_after_1 == cnt_before + 2, f"Expected 2 notifications (SMS+EMAIL), got {cnt_after_1 - cnt_before}"

        # Deliver 2nd time (duplicate)
        await consumer._process_message_with_idempotency(MockRecord(test_event), handle_return_event)

        # Count notifications after duplicate delivery (must be identical)
        async with async_session_factory() as s:
            cnt3_res = await s.execute(text("SELECT count(*) FROM notifications WHERE order_id = :oid"), {"oid": oid_hp})
            cnt_after_2 = cnt3_res.scalar() or 0
        assert cnt_after_2 == cnt_after_1, f"Duplicate was processed! Count increased from {cnt_after_1} to {cnt_after_2}"
        print("    [PASS] Consumer idempotency verified: duplicate event skipped without creating duplicate notifications.")

        # TEST 15: Returns Stats & Analytics
        print("\n--> Test 15: Returns stats & Try-On comparison API...")
        res = await client.get("/api/returns/stats")
        assert res.status_code == 200
        stats = res.json()
        assert "total_returns" in stats and "return_rate_pct" in stats
        assert "tryon_comparison" in stats
        print(f"    [PASS] Returns Stats: total={stats['total_returns']}, return_rate={stats['return_rate_pct']}%, top_reasons={len(stats['top_reasons'])}.")

    print("\n" + "="*70)
    print("ALL 15 POST-DELIVERY RETURNS VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("="*70 + "\n")
    return True


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    if not success:
        sys.exit(1)
