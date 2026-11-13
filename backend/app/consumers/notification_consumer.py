"""Notification consumer: listens to orders.placed, logs/simulates email & SMS,
and records order confirmation records in the notifications table for UI display.
"""

from __future__ import annotations

import asyncio
import uuid
import structlog
from typing import Any, Dict
from sqlalchemy import text

from app.database import async_session_factory
from app.consumers.base_consumer import IdempotentKafkaConsumer

logger = structlog.stdlib.get_logger(__name__)


async def handle_order_placed(event: Dict[str, Any]):
    """Process an order.placed event: generate SMS and Email notifications in database."""
    order_id = event.get("order_id")
    customer_id = event.get("customer_id")
    city = event.get("city")
    total_inr = event.get("total_inr", 0)
    items = event.get("items", [])

    logger.info("processing_order_placed_notification", order_id=order_id, total=total_inr)

    # Fetch customer contact details
    async with async_session_factory() as session:
        cust_res = await session.execute(
            text("SELECT name, email, phone FROM customers WHERE id = :cid"),
            {"cid": customer_id},
        )
        customer = cust_res.mappings().first()

    cust_name = customer["name"] if customer else "Customer"
    cust_phone = customer["phone"] if customer else "+91-9876543210"
    cust_email = customer["email"] if customer else "user@mystore.in"

    item_names = [f"{it.get('quantity', 1)}x {it.get('product_name', 'Item')}" for it in items[:2]]
    items_summary = ", ".join(item_names)
    if len(items) > 2:
        items_summary += f" + {len(items) - 2} more"

    sms_text = f"Namaste {cust_name}! Your MyStore order #{str(order_id)[:8]} for {items_summary} (Rs {total_inr}) is confirmed for delivery in {city}. Track live on MyStore."
    email_text = f"Dear {cust_name},\n\nThank you for shopping at MyStore! Your order #{order_id} has been received and scheduled for dispatch to {city}.\nTotal Paid: Rs {total_inr:,.2f}\nItems:\n" + "\n".join([f"- {it.get('product_name')} (Qty: {it.get('quantity')}) @ Rs {it.get('unit_price_inr')}" for it in items])

    # Insert notifications into PostgreSQL for UI
    async with async_session_factory() as session:
        # SMS Notification
        await session.execute(
            text("""
                INSERT INTO notifications (id, order_id, type, channel, message, created_at)
                VALUES (:id, :oid, 'order_confirmation', 'SMS', :msg, NOW())
            """),
            {"id": uuid.uuid4(), "oid": uuid.UUID(order_id), "msg": sms_text},
        )

        # Email Notification
        await session.execute(
            text("""
                INSERT INTO notifications (id, order_id, type, channel, message, created_at)
                VALUES (:id, :oid, 'order_receipt', 'EMAIL', :msg, NOW())
            """),
            {"id": uuid.uuid4(), "oid": uuid.UUID(order_id), "msg": email_text},
        )
        await session.commit()

    logger.info("simulated_notification_sent", order_id=order_id, sms_to=cust_phone, email_to=cust_email)


async def run_notification_consumer():
    consumer = IdempotentKafkaConsumer(
        consumer_name="notification-consumer",
        topic="orders.placed",
        group_id="mystore-notification-group",
    )
    await consumer.start(handler=handle_order_placed)


if __name__ == "__main__":
    asyncio.run(run_notification_consumer())

