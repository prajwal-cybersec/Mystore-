"""Returns notification consumer: listens to returns.events topic, generates SMS and EMAIL notifications,
and records them in the notifications table for customer visibility.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict
import structlog
from sqlalchemy import text

from app.consumers.base_consumer import IdempotentKafkaConsumer
from app.database import async_session_factory

logger = structlog.stdlib.get_logger(__name__)

STATUS_DESCRIPTIONS = {
    "requested": "Your return request {reference} has been received and is under review.",
    "approved": "Your return request {reference} has been approved. Pickup will be scheduled shortly.",
    "rejected": "Your return request {reference} was rejected. Please contact support for assistance.",
    "cancelled": "Your return request {reference} has been cancelled.",
    "pickup_scheduled": "Pickup scheduled for {reference}. Keep the item safely packed.",
    "picked_up": "Your return item for {reference} has been picked up by our courier partner.",
    "received": "Return item for {reference} has been received at our warehouse for inspection.",
    "refunded": "Refund of Rs {amount:,.2f} for return {reference} has been processed.",
    "replacement_shipped": "Replacement for return {reference} has been dispatched.",
}


async def handle_return_event(event: Dict[str, Any]):
    """Process a return event: generate SMS and Email notifications in database."""
    event_type = event.get("event_type", "")
    return_id = event.get("return_id")
    reference = event.get("reference", "N/A")
    order_id = event.get("order_id")
    customer_id = event.get("customer_id")
    status = event.get("status", "")
    refund_amt = float(event.get("refund_amount_inr", 0.0) or 0.0)
    product_name = event.get("product_name", "Item")

    logger.info("processing_return_event_notification", event_type=event_type, reference=reference, status=status)

    if not order_id:
        logger.warning("return_event_missing_order_id", event_id=event.get("event_id"))
        return

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

    template = STATUS_DESCRIPTIONS.get(
        status,
        f"Update on your return request {reference}: status is now {status}."
    )
    status_msg = template.format(reference=reference, amount=refund_amt)

    sms_text = f"Namaste {cust_name}! {status_msg} Track live in MyStore My Orders."
    email_text = (
        f"Dear {cust_name},\n\n"
        f"This is an update regarding your return request #{reference} for order #{order_id}.\n\n"
        f"Product: {product_name}\n"
        f"Current Status: {status.upper()}\n"
        f"Details: {status_msg}\n\n"
        f"Thank you for shopping with MyStore!"
    )

    async with async_session_factory() as session:
        # SMS Notification
        await session.execute(
            text("""
                INSERT INTO notifications (id, order_id, type, channel, message, created_at)
                VALUES (:id, :oid, 'return_status_update', 'SMS', :msg, NOW())
            """),
            {"id": uuid.uuid4(), "oid": uuid.UUID(order_id), "msg": sms_text},
        )

        # Email Notification
        await session.execute(
            text("""
                INSERT INTO notifications (id, order_id, type, channel, message, created_at)
                VALUES (:id, :oid, 'return_status_update', 'EMAIL', :msg, NOW())
            """),
            {"id": uuid.uuid4(), "oid": uuid.UUID(order_id), "msg": email_text},
        )
        await session.commit()

    logger.info("simulated_return_notification_sent", reference=reference, sms_to=cust_phone, email_to=cust_email)


async def run_returns_notification_consumer():
    consumer = IdempotentKafkaConsumer(
        consumer_name="returns-notification-consumer",
        topic="returns.events",
        group_id="mystore-returns-notification-group",
    )
    await consumer.start(handler=handle_return_event)


if __name__ == "__main__":
    asyncio.run(run_returns_notification_consumer())
