"""Notification consumer: Aggregates multi-seller notifications and sends
ONE consolidated email & SMS once ALL invoices for the order are generated.

Rule 8: Send ONE confirmation email/SMS when ALL invoices for the order are ready
(invoices_ready == invoices_expected). Include every seller's invoice number.
Never send N emails for one order.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict
import structlog
from sqlalchemy import text

from app.database import async_session_factory
from app.consumers.base_consumer import IdempotentKafkaConsumer

logger = structlog.stdlib.get_logger(__name__)


async def handle_invoice_generated(event: Dict[str, Any]):
    """Triggered on invoice.generated. If all invoices for the order are ready,
    sends exactly ONE aggregated notification covering all sellers and packages.
    """
    order_id = event.get("order_id")
    if not order_id:
        return

    oid = uuid.UUID(str(order_id))

    async with async_session_factory() as session:
        async with session.begin():
            # 1. Check order readiness
            ord_res = await session.execute(
                text("SELECT id, customer_id, city, grand_total, total_inr, invoices_expected, invoices_ready FROM orders WHERE id = :oid"),
                {"oid": oid},
            )
            order = ord_res.mappings().first()
            if not order:
                logger.warning("order_not_found_for_notification", order_id=str(oid))
                return

            invoices_expected = order["invoices_expected"] or 1
            invoices_ready = order["invoices_ready"] or 0

            # Only send when ALL invoices are ready
            if invoices_ready < invoices_expected:
                logger.info(
                    "waiting_for_remaining_invoices",
                    order_id=str(oid),
                    ready=invoices_ready,
                    expected=invoices_expected,
                )
                return

            # 2. Idempotency check: Ensure we haven't already sent notification for this order
            notif_check = await session.execute(
                text("SELECT count(*) FROM notifications WHERE order_id = :oid AND type = 'order_confirmation'"),
                {"oid": oid},
            )
            already_sent = (notif_check.scalar() or 0) > 0
            if already_sent:
                logger.info("order_notification_already_sent", order_id=str(oid))
                return

            # 3. Fetch Customer Details
            cust_res = await session.execute(
                text("SELECT name, email, phone FROM customers WHERE id = :cid"),
                {"cid": order["customer_id"]},
            )
            customer = cust_res.mappings().first()
            cust_name = customer["name"] if customer else "Customer"
            cust_phone = customer["phone"] if customer else "+91-9876543210"
            cust_email = customer["email"] if customer else "user@mystore.in"

            # 4. Fetch All Sub-Orders, Invoices, Sellers & Shipments
            pkg_res = await session.execute(
                text("""
                    SELECT so.id as sub_order_id, so.subtotal, so.city as package_city,
                           s.name as seller_name, s.seller_code,
                           i.invoice_no, i.total as invoice_total,
                           sh.tracking_number
                    FROM sub_orders so
                    JOIN sellers s ON s.id = so.seller_id
                    LEFT JOIN invoices i ON i.sub_order_id = so.id
                    LEFT JOIN shipments sh ON sh.sub_order_id = so.id
                    WHERE so.order_id = :oid
                    ORDER BY so.created_at ASC
                """),
                {"oid": oid},
            )
            packages = pkg_res.mappings().all()

            # 5. Fetch All Order Items grouped by sub_order
            item_res = await session.execute(
                text("""
                    SELECT oi.sub_order_id, oi.quantity, oi.unit_price_inr, p.name as product_name
                    FROM order_items oi
                    JOIN products p ON p.id = oi.product_id
                    WHERE oi.order_id = :oid
                """),
                {"oid": oid},
            )
            items = item_res.mappings().all()
            items_by_so: Dict[uuid.UUID, list] = {}
            for it in items:
                items_by_so.setdefault(it["sub_order_id"], []).append(it)

            grand_total = float(order["grand_total"] or order["total_inr"] or 0)
            city = order["city"]
            inv_numbers = [p["invoice_no"] for p in packages if p["invoice_no"]]
            inv_summary = ", ".join(inv_numbers)

            # Build SMS
            sms_text = (
                f"Namaste {cust_name}! Your MyStore order #{str(oid)[:8]} "
                f"({len(packages)} packages from {len(packages)} sellers, Grand Total: Rs {grand_total:,.2f}) "
                f"is confirmed for delivery in {city}. "
                f"Tax Invoices: {inv_summary}. "
                f"Download all invoices at mystore.in/orders/{str(oid)}"
            )

            # Build Email
            email_lines = [
                f"Dear {cust_name},",
                "",
                f"Thank you for your order #{oid} on MyStore!",
                f"Delivery City: {city}",
                f"Grand Total Paid: Rs {grand_total:,.2f}",
                "",
                f"--- CONSOLIDATED PACKAGE & SELLER SUMMARY ({len(packages)} Packages) ---",
            ]

            for idx, pkg in enumerate(packages, 1):
                email_lines.append(f"\n[Package {idx}] Sold by: {pkg['seller_name']}")
                email_lines.append(f"  • Tax Invoice: {pkg['invoice_no'] or 'Pending'}")
                email_lines.append(f"  • Tracking: {pkg['tracking_number'] or 'Assigned'}")
                email_lines.append(f"  • Subtotal: Rs {float(pkg['invoice_total'] or pkg['subtotal']):,.2f}")
                email_lines.append("  • Items:")
                pkg_items = items_by_so.get(pkg["sub_order_id"], [])
                for pi in pkg_items:
                    email_lines.append(f"     - {pi['product_name']} x {pi['quantity']} @ Rs {float(pi['unit_price_inr']):,.2f}")

            email_lines.append("\nYou can download all seller tax invoices with one click at:")
            email_lines.append(f"https://mystore.in/orders/{oid}/invoices.pdf")
            email_lines.append("\nWarm regards,\nMyStore Team")
            email_text = "\n".join(email_lines)

            # 6. Insert exactly ONE SMS and ONE Email notification
            await session.execute(
                text("""
                    INSERT INTO notifications (id, order_id, type, channel, message, created_at)
                    VALUES (:id, :oid, 'order_confirmation', 'SMS', :msg, NOW())
                """),
                {"id": uuid.uuid4(), "oid": oid, "msg": sms_text},
            )

            await session.execute(
                text("""
                    INSERT INTO notifications (id, order_id, type, channel, message, created_at)
                    VALUES (:id, :oid, 'order_receipt', 'EMAIL', :msg, NOW())
                """),
                {"id": uuid.uuid4(), "oid": oid, "msg": email_text},
            )

            logger.info(
                "aggregated_notification_sent",
                order_id=str(oid),
                packages_count=len(packages),
                invoices=inv_numbers,
                sms_to=cust_phone,
                email_to=cust_email,
            )


# Keep backward-compatibility for direct order_placed callers
async def handle_order_placed(event: Dict[str, Any]):
    """If called with order.placed, delegate to invoice check or fallback if single-seller."""
    order_id = event.get("order_id")
    if order_id:
        await handle_invoice_generated({"order_id": order_id})


def create_notification_consumer(group_id: str = "mystore-notification-group") -> IdempotentKafkaConsumer:
    """Consumer configured for invoice.generated topic."""
    return IdempotentKafkaConsumer(
        consumer_name="notification-aggregator",
        topic="invoice.generated",
        group_id=group_id,
    )


async def run_notification_consumer():
    consumer = create_notification_consumer()
    await consumer.start(handler=handle_invoice_generated)


if __name__ == "__main__":
    asyncio.run(run_notification_consumer())
